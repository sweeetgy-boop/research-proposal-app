"""표 사실 적재 유스케이스 (P2-8) — 가짜 TableSourcePort + InMemoryRepository. 파일·DB 없음."""

from __future__ import annotations

from rra.application.ports import TableSourcePort
from rra.application.usecases.extract_facts import ExtractTableFacts
from rra.domain.models import Document, ParsedTable
from tests.fakes import InMemoryRepository

STATION = [
    ["역별 승강설비 현황"],
    ["연 번", "노선명", "역 명", "엘리베이터", "에스컬레이터"],
    ["1", "경부선", "서울역사", "18", "23"],
]
LINES = ["(단위: 억원)", "구분 2023 2024", "매출액 5,100 5,300"]


class FakeTables:
    name = "korail_web"

    def __init__(self, tables):
        self._tables = tables
        self.calls = []

    async def tables(self, *, limit=None):
        self.calls.append(limit)
        return self._tables if limit is None else self._tables[:limit]


def make_repo():
    repo = InMemoryRepository()
    repo.seed(
        [Document(doc_id="korail_web:a", source="korail_web", doc_type="policy", title="승강설비")],
        [],
    )
    return repo


async def test_tables_become_facts_grouped_per_document_and_missing_docs_are_reported():
    source = FakeTables(
        [
            ParsedTable(doc_id="korail_web:a", rows=STATION, sheet="현황"),
            ParsedTable(
                doc_id="korail_web:a", rows=STATION, sheet="현황"
            ),  # 같은 표 두 번 → 중복 제거
            ParsedTable(doc_id="korail_web:zz", lines=LINES, page=2),  # 아직 적재되지 않은 문서
            ParsedTable(doc_id="korail_web:a", rows=[["문장만"], ["또 문장"]]),  # 사실 없음
        ]
    )
    assert isinstance(source, TableSourcePort)
    repo = make_repo()
    report = await ExtractTableFacts(source, repo, repo)()
    assert report.tables == 4 and report.empty_tables == 1 and report.documents == 2
    assert report.facts == 4 and report.by_basis == {"text": 4}
    assert report.missing_docs == ["korail_web:zz"]
    stored = await repo.facts_for(["korail_web:a", "korail_web:zz"])
    assert {f.item for f in stored["korail_web:a"]} == {
        "경부선 서울역사 엘리베이터",
        "경부선 서울역사 에스컬레이터",
    }
    assert [(f.item, f.year, f.unit, f.page) for f in stored["korail_web:zz"]] == [
        ("매출액", 2023, "억원", 2),
        ("매출액", 2024, "억원", 2),
    ]
    assert report.summary()["missing_doc_ids"] == ["korail_web:zz"]
    assert len(report.samples) == 4 and report.samples[0].trust == "untrusted"


async def test_dry_run_stores_nothing_and_rerun_replaces_old_facts():
    repo = make_repo()
    source = FakeTables([ParsedTable(doc_id="korail_web:a", rows=STATION)])
    usecase = ExtractTableFacts(source, repo, repo)
    report = await usecase(dry_run=True, limit=1)
    assert report.dry_run and report.facts == 2 and source.calls == [1]
    assert await repo.facts_for(["korail_web:a"]) == {}
    await usecase()
    assert len((await repo.facts_for(["korail_web:a"]))["korail_web:a"]) == 2
    # 다시 돌리면 통째 교체 — 누적되지 않는다
    await usecase()
    assert len((await repo.facts_for(["korail_web:a"]))["korail_web:a"]) == 2
    assert await repo.fact_counts() == {"korail_web": 2}
