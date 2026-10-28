"""Q8 reranker 포트 — 하이브리드 검색 상위 후보(k×4)를 cross-encoder 로 다시 순위 매긴다.

어댑터(adapters/reranking)는 모델을 ~/models 에서 올리고 블로킹 계산을 스레드로 넘긴다.
precheck(find_similar 의 문서)·섹션별 검색·과제 추천 근거에 모두 쓸 수 있다.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from rra.domain.models import Chunk, Document


@runtime_checkable
class RerankerPort(Protocol):
    model_name: str

    async def rerank(self, query: str, chunks: list[Chunk], *, k: int | None = None) -> list[Chunk]:
        """질의-청크 관련도 순으로 정렬(상위 k). similarity 는 바꾸지 않는다."""
        ...

    async def rerank_documents(
        self, query: str, docs: list[tuple[Document, float]], *, k: int | None = None
    ) -> list[tuple[Document, float]]:
        """precheck 용 — (문서, 유사도) 목록을 다시 정렬. 유사도 값은 그대로 둔다(임계치 판정용)."""
        ...


@runtime_checkable
class DocumentScorerPort(Protocol):
    """precheck 판정용 점수 — (문서, 유사도) 목록의 입력 순서대로 reranker 점수(0~1). 있으면 이
    점수가
    차단 판단의 주 점수다 (2026-10-28 레인 A). RerankerPort 어댑터가 함께 구현할 수 있다."""

    async def score_documents(
        self, query: str, docs: list[tuple[Document, float]]
    ) -> list[float]: ...


def rerank_stats(reranker: Any) -> dict[str, float | int]:
    """어댑터의 집계 속성(calls·seconds·max_batch)이 있으면 읽는다 — 지연 측정용(Q9)."""
    return {
        "calls": int(getattr(reranker, "calls", 0) or 0),
        "seconds": float(getattr(reranker, "seconds", 0.0) or 0.0),
        "max_batch": int(getattr(reranker, "max_batch", 0) or 0),
    }
