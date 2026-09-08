from __future__ import annotations

from typing import Protocol


class EmbeddingPort(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        """색인 대상 문서(passage) 임베딩."""
        ...

    def embed_query(self, texts: list[str]) -> list[list[float]]:
        """검색 질의(query) 임베딩. e5 계열은 passage 와 접두어가 다르다."""
        ...
