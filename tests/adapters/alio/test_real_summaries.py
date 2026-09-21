"""실제 알리오 공개 요약 복사본 — tests/fixtures/alio/summary/expected.yaml 기준. 없으면 skip.

설정(config/sources.yaml 의 alio.summary·own_unit·institutions)을 그대로 읽어 운영과 같은 조건으로.
"""

from datetime import date
from pathlib import Path

import pytest
import yaml

from rra.adapters.sources._sandbox import SandboxLimits, run_parser
from rra.adapters.sources.alio._models import TextLines
from rra.adapters.sources.alio.filecheck import open_validated
from rra.adapters.sources.alio.summary import (
    DEFAULT_LABELS,
    DEFAULT_MAX_BYTES,
    FILE_FORMATS,
    normalize_summary,
    parse_labeled,
)
from rra.domain.rules.overlap import OwnUnit, judge, tier_of

ROOT = Path(__file__).parents[3]
SUMMARY = ROOT / "tests" / "fixtures" / "alio" / "summary"
EXPECTED = yaml.safe_load((SUMMARY / "expected.yaml").read_text(encoding="utf-8")) or {}
CASES = EXPECTED.get("files") or []
CONFIG = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8")) or {}
SUMMARY_CFG = (CONFIG.get("alio") or {}).get("summary") or {}
LABELS = {**DEFAULT_LABELS, **(SUMMARY_CFG.get("labels") or {})}
INSTITUTIONS = CONFIG.get("institutions") or []
OWN_CFG = CONFIG.get("own_unit") or {}
OWN = OwnUnit(
    org=OWN_CFG.get("org", "korail"), departments=frozenset(OWN_CFG.get("departments") or [])
)
LIMITS = SandboxLimits.from_security_config(
    yaml.safe_load((ROOT / "config" / "security.yaml").read_text(encoding="utf-8"))
)


def test_every_real_summary_has_expectations():
    listed = {c["file"] for c in CASES}
    present = {p.name for p in SUMMARY.iterdir() if p.suffix.lower() == ".txt"}
    assert present <= listed, f"expected.yaml 에 없는 파일: {sorted(present - listed)}"


async def _load(case):
    with open_validated(
        SUMMARY / case["file"], max_bytes=DEFAULT_MAX_BYTES, allowed=FILE_FORMATS
    ) as vf:
        if case.get("sha256"):
            assert vf.sha256 == case["sha256"], "파일이 바뀌었다 — expected.yaml 을 갱신할 것"
        lines = TextLines.model_validate(await run_parser(vf.fd, vf.fmt, LIMITS)).lines
        return vf.sha256, lines


def _doc(sha, lines):
    return normalize_summary(
        {"sha256": sha, "lines": lines, "catalog": None},
        labels=LABELS,
        institutions=INSTITUTIONS,
        default_org=SUMMARY_CFG.get("default_org"),
    )


@pytest.mark.skipif(not CASES, reason="실제 공개 요약 미투입 (tests/fixtures/alio/README.md)")
@pytest.mark.parametrize("case", CASES, ids=[c["file"] for c in CASES])
async def test_real_summary(case):
    sha, lines = await _load(case)  # 실제 샌드박스를 거친다
    fields = parse_labeled(lines, LABELS)
    missing = [f for f in case.get("fields") or [] if f not in fields]
    assert not missing, f"라벨을 못 잡은 필드: {missing} — sources.yaml alio.summary.labels 확인"
    assert not [f for f in case.get("absent") or [] if f in fields]

    doc = _doc(sha, lines)
    assert doc.text_basis == "summary" and doc.trust == "untrusted"
    assert doc.title == case["title"]
    assert doc.pub_date == date.fromisoformat(str(case["published"]))
    assert doc.authors == case["authors"]
    assert doc.raw["project_type"] == case["project_type"]
    assert doc.raw["pi"] == case["pi"]
    assert doc.department == case["department"]
    assert doc.project_period == tuple(date.fromisoformat(str(d)) for d in case["period"])
    assert doc.raw["budget_krw"] == case["budget_krw"]
    assert doc.raw["disclosure"]["status"] == case["disclosure_status"]
    assert doc.raw["disclosure"]["open_date"] == case["open_date"]
    assert doc.toc == [f"■ {h}" for h in case["sections"]]
    assert doc.orgs == case["orgs"] and doc.raw["org_source"] == case["org_source"]
    # 본문 절이 빠짐없이 들어가고, 절 사이 경계가 섞이지 않았다
    for heading in case["sections"]:
        assert f"■ {heading}\n- " in doc.body
    assert "* " not in doc.body and "과제개요" not in doc.body


@pytest.mark.skipif(not CASES, reason="실제 공개 요약 미투입 (tests/fixtures/alio/README.md)")
@pytest.mark.parametrize("case", CASES, ids=[c["file"] for c in CASES])
async def test_real_summary_overlap_tier(case):
    doc = _doc(*(await _load(case)))
    assert tier_of(doc, OWN) == case["tier"]
    # precheck 경보에서도 같은 티어·임계치(own 0.80)가 적용된다
    (alert,) = judge([(doc, 0.81)], own=OWN)
    assert alert.tier == case["tier"] and alert.basis == "summary"
    assert alert.blocking is (case["tier"] == "own")
