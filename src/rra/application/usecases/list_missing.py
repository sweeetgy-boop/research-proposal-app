"""알리오 카탈로그 중 수동 다운로드가 필요한 보고서.

- `__call__`: 아직 DB 에 없는 항목.
- `upgradable`: 공개 요약만 적재돼 있는데 원문이 공개된(공개예정일 경과) 항목.
"""

from __future__ import annotations

from datetime import date

from rra.application.ports import CatalogPort, DocumentRepository
from rra.domain.models import CatalogEntry
from rra.domain.rules.disclosure import original_obtainable


class ListMissing:
    def __init__(self, catalog: CatalogPort, repo: DocumentRepository):
        self.catalog, self.repo = catalog, repo

    async def __call__(self) -> list[CatalogEntry]:
        get = self.repo.get_document
        return [e for e in await self.catalog.entries() if get(f"alio:{e.catalog_id}") is None]

    async def upgradable(self, today: date) -> list[CatalogEntry]:
        out = []
        for e in await self.catalog.entries():
            doc = self.repo.get_document(f"alio:{e.catalog_id}")
            if doc is not None and original_obtainable(doc, today):
                out.append(e)
        return out
