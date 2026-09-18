"""알리오 카탈로그 중 아직 DB 에 없는 보고서 목록 (수동 다운로드 대상)."""

from __future__ import annotations

from rra.application.ports import CatalogPort, DocumentRepository
from rra.domain.models import CatalogEntry


class ListMissing:
    def __init__(self, catalog: CatalogPort, repo: DocumentRepository):
        self.catalog, self.repo = catalog, repo

    async def __call__(self) -> list[CatalogEntry]:
        get = self.repo.get_document
        return [e for e in await self.catalog.entries() if get(f"alio:{e.catalog_id}") is None]
