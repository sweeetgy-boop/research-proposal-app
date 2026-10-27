"""② 유사과제 사전 확인 — find_similar(k) → 판정(domain/rules/overlap.judge).

Q8 reranker 가 있으면 k×rerank_multiplier 를 받아 cross-encoder 로 다시 순위 매긴 상위 k 로 판정한다
(유사도 값은 그대로 — 임계치 판정용).
"""

from __future__ import annotations

from typing import Any

from rra.application.ports import DocumentRepository
from rra.domain.models import OverlapAlert, ProposalRequest
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.overlap import OwnUnit, judge


class PrecheckOverlap:
    def __init__(
        self,
        repo: DocumentRepository,
        k: int = 10,
        own: OwnUnit | None = None,
        keywords: KeywordRule | None = None,
        reranker: Any | None = None,
        rerank_multiplier: int = 4,
    ):
        self.repo, self.k, self.own, self.keywords = repo, k, own, keywords
        self.reranker, self.rerank_multiplier = reranker, rerank_multiplier

    async def __call__(self, req: ProposalRequest) -> list[OverlapAlert]:
        query = req.search_text()
        if self.reranker is None:
            hits = await self.repo.find_similar(query, k=self.k)
        else:
            wide = await self.repo.find_similar(query, k=self.k * self.rerank_multiplier)
            hits = list(await self.reranker.rerank_documents(query, list(wide), k=self.k))
        return judge(hits, own=self.own, query=query, keywords=self.keywords)
