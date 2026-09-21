"""list_missing 유스케이스 — 카탈로그 중 DB 에 없는 항목만."""

from rra.application.usecases.list_missing import ListMissing
from rra.domain.models import CatalogEntry
from tests.fakes import FakeCatalog, InMemoryRepository


def entry(cid):
    return CatalogEntry(catalog_id=cid, institution_tag="korail", title=f"보고서 {cid}")


async def test_lists_only_entries_not_in_repo(docs):
    repo = InMemoryRepository()
    repo.upsert([docs[0]], [])  # alio:1 은 이미 적재
    missing = await ListMissing(FakeCatalog([entry("1"), entry("2")]), repo)()
    assert [e.catalog_id for e in missing] == ["2"]


async def test_empty_catalog():
    assert await ListMissing(FakeCatalog([]), InMemoryRepository())() == []


def summary_doc(cid, disclosure):
    from rra.domain.models import Document

    return Document(
        doc_id=f"alio:{cid}",
        source="alio",
        doc_type="internal_report",
        title=f"보고서 {cid}",
        body="요약",
        text_basis="summary",
        raw={"disclosure": disclosure},
    )


async def test_upgradable_lists_summaries_whose_original_opened(docs):
    from datetime import date

    repo = InMemoryRepository()
    repo.upsert(
        [
            summary_doc("a", {"status": "비공개", "open_date": "2026-01-01"}),  # 경과
            summary_doc("b", {"status": "비공개", "open_date": "2027-01-01"}),  # 미경과
            summary_doc("c", {"status": "공개"}),
            summary_doc("d", {"status": "비공개"}),  # 예정일 없음
            docs[0],  # alio:1 원문
        ],
        [],
    )
    ids = ["a", "b", "c", "d", "1", "z"]
    out = await ListMissing(FakeCatalog([entry(i) for i in ids]), repo).upgradable(
        date(2026, 9, 21)
    )
    assert [e.catalog_id for e in out] == ["a", "c"]
