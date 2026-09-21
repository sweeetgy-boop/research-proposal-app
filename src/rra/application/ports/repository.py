from __future__ import annotations

from typing import Protocol

from rra.domain.models import Chunk, Document


class DocumentRepository(Protocol):
    def upsert(self, docs: list[Document], chunks: list[Chunk]) -> None: ...

    def hybrid_search(
        self, queries: list[str], *, k: int = 20, orgs: list[str] | None = None
    ) -> list[Chunk]: ...

    def find_similar(self, text: str, *, k: int = 10) -> list[tuple[Document, float]]: ...

    def get_document(self, doc_id: str) -> Document | None: ...

    def count_by_source(self) -> dict[str, int]:
        """자료원별 적재 문서 수. 한 건도 없는 자료원은 키가 없다."""
        ...
