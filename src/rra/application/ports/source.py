from __future__ import annotations

from typing import Any, Protocol

from rra.domain.models import Document


class SourcePort(Protocol):
    source: str

    async def search(self, query: str | None, limit: int) -> list[dict[str, Any]]:
        """원본 응답 반환. query=None 이면 증분 수집."""
        ...

    def normalize(self, raw: dict[str, Any]) -> Document:
        """순수 함수. 네트워크 접근 금지."""
        ...
