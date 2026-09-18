"""실제 알리오 공시 파일 — tests/fixtures/alio/real/expected.yaml 기준. 파일이 없으면 skip."""

import os
from pathlib import Path

import pytest
import yaml

from rra.adapters.sources._sandbox import SandboxLimits, run_parser
from rra.adapters.sources.alio._models import ExtractResult
from rra.adapters.sources.alio.filecheck import open_validated
from rra.adapters.sources.alio.filedrop import FILE_FORMATS, normalize_report

ROOT = Path(__file__).parents[3]
REAL = ROOT / "tests" / "fixtures" / "alio" / "real"
EXPECTED = yaml.safe_load((REAL / "expected.yaml").read_text(encoding="utf-8")) or {}
CASES = EXPECTED.get("files") or []
LIMITS = SandboxLimits.from_security_config(
    yaml.safe_load((ROOT / "config" / "security.yaml").read_text(encoding="utf-8"))
)


def test_every_real_file_has_expectations():
    listed = {c["file"] for c in CASES}
    present = {p.name for p in REAL.iterdir() if p.suffix.lower().lstrip(".") in FILE_FORMATS}
    assert present <= listed, f"expected.yaml 에 없는 파일: {sorted(present - listed)}"


@pytest.mark.skipif(not CASES, reason="실제 공시 파일 미투입 (tests/fixtures/alio/README.md)")
@pytest.mark.parametrize("case", CASES, ids=[c["file"] for c in CASES])
async def test_real_report(case):
    path = REAL / case["file"]
    with open_validated(
        path, max_bytes=int(LIMITS.max_input_mb * 1024 * 1024), allowed=FILE_FORMATS
    ) as vf:
        assert vf.fmt == case["fmt"]
        if case.get("sha256"):
            assert vf.sha256 == case["sha256"], "파일이 바뀌었다 — expected.yaml 을 갱신할 것"
        result = ExtractResult.model_validate(await run_parser(vf.fd, vf.fmt, LIMITS))
        sha = vf.sha256

    if "pages" in case:
        assert result.pages == case["pages"]
    assert len(result.toc) >= int(case.get("toc_min", 0))
    assert len(result.text) >= int(case.get("min_chars", 1))
    for needle in case.get("text_contains") or []:
        assert needle in result.text, needle

    doc = normalize_report(
        {"sha256": sha, "fmt": vf.fmt, "catalog": None, "extract": result.model_dump()}
    )
    assert doc.doc_id == f"alio:sha-{sha[:16]}" and doc.trust == "untrusted"
    if case.get("title_contains"):
        assert case["title_contains"] in doc.title
    assert os.path.basename(str(path)) not in repr(doc.raw)  # 파일명은 문서에 남기지 않는다
