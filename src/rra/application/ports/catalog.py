from __future__ import annotations

from typing import Protocol

from rra.domain.models import CatalogEntry


class CatalogPort(Protocol):
    async def entries(self) -> list[CatalogEntry]:
        """대상 기관으로 걸러진 카탈로그 항목."""
        ...
