"""실응답 fixture 로 ScienceON·NTIS 정규화 확인. 없으면 skip (tests/fixtures/*/README.md).

필드 매핑(scienceon/normalize.py·ntis/projects.py 의 FIELDS 후보)을 여기서 실응답으로 확정한다.
"""

from pathlib import Path

import pytest
import yaml

from rra.adapters.sources._xml import find_records, flatten, parse
from rra.adapters.sources.ntis import normalize_project
from rra.adapters.sources.scienceon import normalize_record

ROOT = Path(__file__).parents[2]
FIX = ROOT / "tests" / "fixtures"
SOURCES = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))
SCIENCEON = sorted((FIX / "scienceon").glob("*.xml"))
NTIS = sorted((FIX / "ntis").glob("*.xml"))
KIPRIS = sorted((FIX / "kipris").glob("*.xml"))
KIPRIS_TAG = (SOURCES.get("kipris") or {}).get("record_tag") or "PatentUtilityInfo"
NTIS_TAG = (SOURCES.get("ntis") or {}).get("record_tag") or ""


def test_fixtures_hold_no_obvious_secrets():
    for path in [*SCIENCEON, *NTIS, *KIPRIS]:
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in (
            "accounts=",
            "apprvKey=",
            "refreshToken=",
            "token=",
            "accessKey=",
            "ServiceKey=",
        ):
            assert marker not in text, f"{path.name}: {marker}"


def _scienceon_target(path: Path) -> str:
    return next((t for t in ("REPORT", "PATENT", "ARTI") if f"_{t}_" in path.name), "ARTI")


def test_scienceon_fixtures_recorded():
    """2026-10-27 실응답 녹화 — ARTI·REPORT·PATENT 각 1건이 있어야 매핑 테스트가 돈다."""
    assert {_scienceon_target(p) for p in SCIENCEON} == {"ARTI", "REPORT", "PATENT"}


def test_scienceon_fixtures_hold_no_person_names():
    """사람 이름 항목은 녹화 도구가 NAME-REMOVED 로 바꾼다 (기관명은 남는다)."""
    for path in SCIENCEON:
        for r in find_records(parse(path.read_bytes()), "record"):
            flat = flatten(r)
            for code in ("Author", "Author2", "Contributors"):
                assert flat.get(code, "") in {"", "NAME-REMOVED"}, f"{path.name}: {code}"


@pytest.mark.parametrize("path", SCIENCEON, ids=[p.name for p in SCIENCEON])
def test_scienceon_records_normalize(path):
    target = _scienceon_target(path)
    records = [
        {"target": target, **flatten(r)} for r in find_records(parse(path.read_bytes()), "record")
    ]
    assert len(records) == 10, "rowCount=10 으로 녹화했다"
    docs = [normalize_record(r, SOURCES.get("institutions") or []) for r in records]
    assert len({d.doc_id for d in docs}) == len(docs)
    assert all(d.title and d.source == "scienceon" for d in docs)
    assert all(
        d.doc_type == {"ARTI": "paper", "REPORT": "internal_report", "PATENT": "patent"}[target]
        for d in docs
    )
    assert all(not d.authors for d in docs)  # 저자·연구책임자·발명자 이름은 저장하지 않는다
    assert all(d.pub_date and d.url and d.url.startswith("http") for d in docs)
    assert sum(1 for d in docs if d.abstract) >= 8
    assert any(d.raw["orgs_named"] for d in docs)
    assert "NAME-REMOVED" not in " ".join(str(d.model_dump()) for d in docs)
    if target == "ARTI":
        assert sum(1 for d in docs if d.doi) >= 8 and all(
            (d.doi or "10.").startswith("10.") for d in docs
        )
        assert all(d.lang == "ko" for d in docs)
    if target == "REPORT":
        assert all(d.raw["project_no"] for d in docs)
    if target == "PATENT":
        assert all(d.application_no and d.application_no.isdigit() for d in docs)
        assert sum(1 for d in docs if d.codes) >= 8
        assert all(d.raw["status"] for d in docs)
        assert any("krri" in d.orgs for d in docs)  # 한국철도기술연구원 출원 건이 들어 있다


@pytest.mark.skipif(not NTIS, reason="NTIS 실응답 미녹화 (tests/fixtures/ntis/README.md)")
@pytest.mark.skipif(not NTIS_TAG, reason="sources.yaml ntis.record_tag 미설정")
@pytest.mark.parametrize("path", NTIS, ids=[p.name for p in NTIS])
def test_ntis_projects_normalize(path):
    institutions = SOURCES.get("institutions") or []
    records = [flatten(r) for r in find_records(parse(path.read_bytes()), NTIS_TAG)]
    assert records, f"record_tag {NTIS_TAG!r} 요소가 없다"
    docs = [normalize_project(r, institutions) for r in records]
    assert all(d.doc_id.startswith("ntis:") and d.doc_type == "rnd_project" for d in docs)
    assert any(d.abstract for d in docs), "연구목표·내용 필드 매핑을 확인할 것"


@pytest.mark.skipif(not KIPRIS, reason="KIPRIS 실응답 미녹화 (tests/fixtures/kipris/README.md)")
@pytest.mark.parametrize("path", KIPRIS, ids=[p.name for p in KIPRIS])
def test_kipris_records_normalize(path):
    from rra.adapters.sources.kipris import normalize_patent

    records = [flatten(r) for r in find_records(parse(path.read_bytes()), KIPRIS_TAG)]
    assert records, f"{KIPRIS_TAG} 요소가 없다 — sources.yaml kipris.record_tag 를 확인"
    docs = [normalize_patent(r, SOURCES.get("institutions") or []) for r in records]
    assert len({d.doc_id for d in docs}) == len(docs)
    assert all(d.doc_type == "patent" and d.source == "kipris_kr" and d.title for d in docs)
    assert all(not d.authors for d in docs)  # 발명자·개인 출원인 이름은 저장하지 않는다
