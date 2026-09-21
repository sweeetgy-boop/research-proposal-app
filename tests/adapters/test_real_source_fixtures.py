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
NTIS_TAG = (SOURCES.get("ntis") or {}).get("record_tag") or ""


def test_fixtures_hold_no_obvious_secrets():
    for path in [*SCIENCEON, *NTIS]:
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in ("accounts=", "apprvKey=", "refreshToken=", "token="):
            assert marker not in text, f"{path.name}: {marker}"


@pytest.mark.skipif(
    not SCIENCEON, reason="ScienceON 실응답 미녹화 (tests/fixtures/scienceon/README.md)"
)
@pytest.mark.parametrize("path", SCIENCEON, ids=[p.name for p in SCIENCEON])
def test_scienceon_records_normalize(path):
    target = "REPORT" if "_REPORT_" in path.name else "ARTI"
    records = [
        {"target": target, **flatten(r)} for r in find_records(parse(path.read_bytes()), "record")
    ]
    assert records, "record 요소가 없다 — 응답 구조가 가이드와 다르다"
    docs = [normalize_record(r) for r in records]
    assert len({d.doc_id for d in docs}) == len(docs)
    assert all(d.title and d.source == "scienceon" for d in docs)


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
