# ruff: noqa: E501  (실물 시트 모양을 그대로 둔 행 데이터)
"""own_projects — 시트 종류 판별, 행 → Record, 상태 판정, 과제명 병합, Document, 소스."""

from datetime import date
from pathlib import Path

import pytest

from rra.adapters.sources._sandbox import SandboxLimits
from rra.adapters.sources.own.excel import (
    OwnProjectsSource,
    Record,
    assign_status,
    detect_kind,
    merge_records,
    parse_sheet,
    record_document,
)
from rra.application.usecases.ingest_sources import IngestSources
from rra.domain.rules.overlap import OwnUnit, judge
from tests.fakes import InMemoryRepository

TODAY = date(2026, 10, 26)
PROPOSAL = [
    ["연구과제 제안 현황", None, None, None, None, None, None, None],
    [
        "구분",
        "연구분류",
        "연구과제 접수명",
        "제안자",
        "부서",
        "제출일자",
        "진행단계",
        "위원회 결과",
    ],
    [
        "정기과제",
        "기초연구",
        "AI 기반 역사 조명 최적화",
        "홍길동",
        "철도연구원 연구계획처",
        "2025-08-19",
        "미채택",
        "위원회 생략",
    ],
    [
        "자체과제",
        "응용연구",
        "궤도 틀림 상시 감지",
        "김철수",
        "철도연구원 기술연구처",
        "2026-02-01",
        "(2차) 타당성 검토중",
        None,
    ],
    [None, None, None, None, None, None, None, None],
]
STATUS = [
    ["연구과제 현황"],
    [
        "구분",
        "연구분류",
        "연구과제명",
        "연구 시작일자",
        "연구 종료일자",
        "책임연구원",
        "책임연구원 부서",
        "인건비",
        "직접비",
        "총 연구비",
        "계획공정률",
        "진척공정률",
        "연구과제 \n진행상태",
        "업무 진행단계",
        None,
        None,
    ],
    [
        "자체과제",
        "개발연구",
        "궤도 틀림 상시 감지",
        "2026-03-01",
        "2027-02-28",
        "김철수",
        "철도연구원 기술연구처",
        "1",
        "2",
        "150000000",
        "10",
        "5",
        "진행중",
        "승인",
        "x",
        "y",
    ],
    [
        "국가과제",
        "기초연구",
        "전차선 아크 감지",
        "2024-01-01",
        "2025-12-31",
        "이영희",
        "철도연구원 기술연구처",
        None,
        None,
        "80000000.0",
        None,
        None,
        "완료",
        "승인",
        None,
        None,
    ],
]
HISTORY = [
    [None, "144"],
    [
        "NO",
        "연구과제명",
        "연구분류",
        "책임연구원명",
        "책임연구원부서명",
        "연구시작일자",
        "연구종료일자",
        "총연구비",
    ],
    [
        "1",
        "KTX 차량 컴퓨터 제어장치 개발",
        "개발연구",
        "김현식",
        "철도연구원 기술연구처",
        "2005-06-01T00:00:00",
        "2009-12-01T00:00:00",
        "363000000",
    ],
]
PERFORMANCE = [
    [
        None,
        "순번",
        "과제명",
        "담당부서",
        "담당자",
        "추진구분",
        "시작일",
        "종료일",
        "수행비용",
        "비고",
    ],
    [
        None,
        "1",
        "승차권 구매 행태 분석",
        "경영연구처",
        "김한수",
        "자체",
        "2021-01-01",
        "2021-09-30",
        "14999220",
        None,
    ],
    [
        None,
        "2",
        "전차선 아크 감지",
        "기술연구처",
        "박지선",
        "국가",
        "2024-01-01",
        "2025-12-31",
        "80000000",
        None,
    ],
    [
        None,
        "3",
        "중단된 과제",
        "기술연구처",
        "최원규",
        "자체",
        "2026-01-01",
        "2026-12-31",
        "1000",
        "중단",
    ],
    [
        None,
        "4",
        "진행 중 과제",
        "기술연구처",
        "최원규",
        "자체",
        "2026-01-01",
        "2027-12-31",
        "1000",
        None,
    ],
]


def test_detect_kind_by_header_names():
    assert detect_kind(PROPOSAL[1]) == "proposal"
    assert detect_kind(STATUS[1]) == "status"
    assert detect_kind(HISTORY[1]) == "history"
    assert detect_kind(PERFORMANCE[0]) == "performance"
    assert detect_kind(["구분", "2021", "2022"]) is None


def test_parse_sheet_reads_rows_without_name_columns():
    recs = parse_sheet("연구과제 제안 현황", PROPOSAL, file="제안.xls")
    assert [r.title for r in recs] == ["AI 기반 역사 조명 최적화", "궤도 틀림 상시 감지"]
    first = recs[0]
    assert first.kind == "proposal" and first.program == "정기과제" and first.category == "기초연구"
    assert first.department == "철도연구원 연구계획처" and first.submitted == date(2025, 8, 19)
    assert first.stage == "미채택" and first.committee == "위원회 생략" and first.row == 3
    assert "홍길동" not in str(first)
    status = parse_sheet("연구과제 현황", STATUS, file="현황.xls")
    assert status[0].remark == "진행중" and status[0].budget_krw == 150_000_000
    assert status[1].budget_krw == 80_000_000 and status[1].end == date(2025, 12, 31)
    hist = parse_sheet("국가연구(2006-2024)", HISTORY, file="목록.xlsx")
    assert hist[0].program == "국가" and hist[0].start == date(2005, 6, 1)
    assert parse_sheet("연구과제 등", [["구분", "2021"], ["계", "32"]], file="x.xlsx") == []


def test_assign_status_per_kind():
    p = parse_sheet("p", PROPOSAL, file="p.xls")
    assert [assign_status(r, TODAY).status for r in p] == ["rejected", "proposed"]
    s = parse_sheet("s", STATUS, file="s.xls")
    assert [assign_status(r, TODAY).status for r in s] == ["ongoing", "completed"]
    h = parse_sheet("자체연구(2006-2024)", HISTORY, file="h.xlsx")
    assert assign_status(h[0], TODAY).status == "completed"
    perf = parse_sheet("자체과제", PERFORMANCE, file="perf.xlsx")
    assert [assign_status(r, TODAY).status for r in perf] == [
        "completed",
        "completed",
        "stopped",
        "ongoing",
    ]


def _all_records():
    recs = []
    for name, rows, file in (
        ("제안", PROPOSAL, "제안.xls"),
        ("현황", STATUS, "현황.xls"),
        ("국가연구", HISTORY, "목록.xlsx"),
        ("자체과제", PERFORMANCE, "수행.xlsx"),
    ):
        recs.extend(assign_status(r, TODAY) for r in parse_sheet(name, rows, file=file))
    return recs


def test_merge_prefers_performed_record_and_attaches_proposal():
    merged = {r.title: r for r in merge_records(_all_records())}
    assert len(merged) == 7  # 11 행 → 7 과제
    track = merged["궤도 틀림 상시 감지"]
    assert track.kind == "status" and track.status == "ongoing"
    assert (
        track.proposal["stage"] == "(2차) 타당성 검토중" and track.proposal["status"] == "proposed"
    )
    arc = merged["전차선 아크 감지"]
    assert arc.kind == "status" and arc.proposal is None  # status > performance
    assert merged["AI 기반 역사 조명 최적화"].kind == "proposal"
    assert merged["중단된 과제"].status == "stopped"


def test_record_document_fields_visibility_and_body():
    merged = {r.title: r for r in merge_records(_all_records())}
    doc = record_document(merged["궤도 틀림 상시 감지"])
    assert doc.source == "own" and doc.doc_type == "rnd_project" and doc.doc_id.startswith("own:")
    assert doc.visibility == "internal" and doc.orgs == ["korail"]
    assert doc.department == "철도연구원 기술연구처" and doc.text_basis == "abstract"
    assert doc.project_period == (date(2026, 3, 1), date(2027, 2, 28))
    assert (
        "상태 진행중" in doc.abstract
        and "제안 기록: 제출 2026-02-01 · 진행단계 (2차) 타당성 검토중" in doc.abstract
    )
    assert doc.raw["status"] == "ongoing" and doc.raw["proposal"]["stage"] == "(2차) 타당성 검토중"
    assert "김철수" not in doc.model_dump_json()
    rejected = record_document(merged["AI 기반 역사 조명 최적화"])
    assert rejected.visibility == "internal" and rejected.raw["status"] == "rejected"
    assert "상태 미채택" in rejected.abstract and rejected.pub_date == date(2025, 8, 19)
    public = record_document(merged["KTX 차량 컴퓨터 제어장치 개발"])
    assert public.visibility == "public" and "총연구비 363,000,000원" in public.abstract
    same = record_document(
        Record(kind="history", title="궤도 틀림  상시 감지", file="f", sheet="s")
    )
    assert same.doc_id == doc.doc_id  # 과제명 정규화로 같은 id


def test_judge_exposes_project_status_on_alerts():
    merged = {r.title: r for r in merge_records(_all_records())}
    doc = record_document(merged["AI 기반 역사 조명 최적화"])
    own = OwnUnit(org="korail", departments=frozenset({"연구계획처"}))
    [alert] = judge([(doc, 0.9)], own=own)
    assert alert.tier == "own" and alert.status == "rejected"


def sheets_runner(**by_fmt):
    """fmt 별 시트를 돌려주는 가짜 runner (몇 번이든 호출 가능)."""
    calls = []

    async def run(fd, fmt, lim):
        calls.append(fmt)
        return {"sheets": by_fmt[fmt]}

    run.calls = calls
    return run


async def test_source_reads_files_merges_and_ingests(tmp_path):
    inbox = tmp_path / "own"
    inbox.mkdir()
    (inbox / "1 제안 현황.xls").write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest")
    (inbox / "2 수행현황.xlsx").write_bytes(b"PK\x03\x04rest")
    (inbox / "~$2 수행현황.xlsx").write_bytes(b"PK\x03\x04rest")  # 엑셀 잠금 파일은 무시
    (inbox / "메모.txt").write_text("x", encoding="utf-8")
    run = sheets_runner(
        xls=[{"name": "연구과제 제안 현황", "rows": PROPOSAL}],
        xlsx=[
            {"name": "연구과제 등", "rows": [["구분"]]},
            {"name": "자체과제", "rows": PERFORMANCE},
        ],
    )
    src = OwnProjectsSource(inbox, limits=SandboxLimits(), today=lambda: TODAY, runner=run)
    assert src.inbox_status() == {"pending": 2, "done": 0, "quarantine": 0}
    raws = await src.search(None, 100)
    assert run.calls == ["xls", "xlsx"] and len(raws) == 6
    repo = InMemoryRepository()
    report = await IngestSources(
        [src], repo, own=OwnUnit(org="korail", departments=frozenset({"기술연구처", "경영연구처"}))
    ).__call__()
    assert report.stored == 6 and report.fetched == {"own_projects": 6}
    assert {w.code for w in report.warnings} == {"unlisted_department"}  # 연구계획처
    assert (inbox / "1 제안 현황.xls").exists()  # 목록 파일은 옮기지 않는다
    assert await src.search(None, 0) == []


REAL = Path("data/inbox/own")


@pytest.mark.skipif(
    not (REAL / "연구과제 제안 현황.xls").exists(), reason="실물 엑셀이 data/inbox/own 에 없음"
)
async def test_real_excel_files_parse_in_the_sandbox():
    src = OwnProjectsSource(REAL, limits=SandboxLimits(), today=lambda: TODAY)
    raws = await src.search(None, 10_000)
    kinds = {r["kind"] for r in raws}
    assert {"proposal", "status", "history", "performance"} <= kinds and len(raws) > 1000
    assert any(r["status"] == "rejected" for r in raws) and any(r["proposal"] for r in raws)
    names = {"제안자", "책임연구원", "담당자"}
    assert not any(k in names for r in raws for k in r)
