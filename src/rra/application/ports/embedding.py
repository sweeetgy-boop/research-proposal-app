from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingPort(Protocol):
    """문장 임베딩. dim 은 벡터 차원 — 저장소가 색인 차원 검증에 쓴다.

    구현은 모델 로드를 첫 embed/dim 호출로 미룰 수 있다 (생성만으로 모델을 띄우지 않는다).
    embed/embed_query 는 비동기 — CPU 계산은 스레드로 넘겨 이벤트 루프를 막지 않는다.
    """

    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """색인 대상 문서(passage) 임베딩."""
        ...

    async def embed_query(self, texts: list[str]) -> list[list[float]]:
        """검색 질의(query) 임베딩. e5 계열은 passage 와 접두어가 다르다."""
        ...
