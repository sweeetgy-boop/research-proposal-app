"""DB 유지보수 포트 — 재색인·백업. 구현은 adapters/persistence (SQLite)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from rra.domain.models import Document


@runtime_checkable
class DatabaseMaintenancePort(Protocol):
    async def reindex(self) -> dict[str, Any]:
        """모든 청크를 현재 임베딩 모델로 다시 색인. {"chunks", "dim", "model"}."""
        ...

    async def backup(self, out: str | Path) -> Path:
        """일관된 DB 사본을 out 에 만든다 (덮어쓰지 않음). 만든 경로."""
        ...


@runtime_checkable
class DocumentReclassifyPort(Protocol):
    """자료 분류 이주(`rra db reclassify`, ADR 0040) — 자료원별 문서 읽기와 doc_type·raw 바꾸기만.
    청크·벡터는 건드리지 않는다(본문이 같으므로 재색인 없음)."""

    async def documents_of(self, source: str, *, limit: int | None = None) -> list[Document]: ...

    async def reclassify(self, changes: Sequence[tuple[str, str, dict[str, Any]]]) -> int:
        """(doc_id, doc_type, raw) 목록을 한 트랜잭션으로 반영. 바꾼 행 수."""
        ...
