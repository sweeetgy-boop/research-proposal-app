"""② 유사과제 사전 확인 — find_similar(k) → 판정(domain/rules/overlap.judge).

Q8 reranker 가 있으면 k×rerank_multiplier(기본 3)를 받아 cross-encoder 로 다시 순위 매긴 상위 k 로
판정한다 (유사도 값은 그대로 — 임계치 판정용).
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
        mix: Any | None = None,  # RetrievalMix — overlap_exclude doc_type 은 판정 후보에서 뺀다
        rerank_multiplier: int = 3,  # k×3=30건: MPS 에서 약 1.6s (k×4 는 2.0~2.4s, 2026-10-27)
    ):
        self.repo, self.k, self.own, self.keywords = repo, k, own, keywords
        self.reranker, self.rerank_multiplier, self.mix = reranker, rerank_multiplier, mix

    async def __call__(self, req: ProposalRequest) -> list[OverlapAlert]:
        query = req.search_text()
        if self.reranker is None:
            hits = list(await self.repo.find_similar(query, k=self.k))
            if self.mix is not None:
                hits = self.mix.overlap_candidates(hits, lambda d: d.doc_type)
        else:
            wide = list(await self.repo.find_similar(query, k=self.k * self.rerank_multiplier))
            if self.mix is not None:
                wide = self.mix.overlap_candidates(wide, lambda d: d.doc_type)
            hits = list(await self.reranker.rerank_documents(query, wide, k=self.k))
        return judge(hits, own=self.own, query=query, keywords=self.keywords)
