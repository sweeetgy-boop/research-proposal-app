from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from rra.domain.models import Chunk, Document


@runtime_checkable
class DocumentRepository(Protocol):
    """문서·청크 저장소. 전부 비동기 — 구현은 블로킹 I/O·임베딩 계산을 스레드로 넘겨
    호출자의 이벤트 루프를 막지 않는다."""

    async def upsert(self, docs: list[Document], chunks: list[Chunk]) -> None: ...

    async def hybrid_search(
        self, queries: list[str], *, k: int = 20, orgs: list[str] | None = None
    ) -> list[Chunk]: ...

    async def find_similar(self, text: str, *, k: int = 10) -> list[tuple[Document, float]]: ...

    async def get_document(self, doc_id: str) -> Document | None: ...

    async def count_by_source(self) -> dict[str, int]:
        """자료원별 적재 문서 수. 한 건도 없는 자료원은 키가 없다."""
        ...

    async def source_status(self) -> dict[str, dict[str, Any]]:
        """자료원별 {"count": n, "last_ingested": ISO 날짜 | None}. 없는 자료원은 키가 없다."""
        ...
