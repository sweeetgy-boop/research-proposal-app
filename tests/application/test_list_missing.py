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
