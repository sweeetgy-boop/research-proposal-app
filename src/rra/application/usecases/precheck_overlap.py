"""② 유사과제 사전 확인 — find_similar(k) → 판정(domain/rules/overlap.judge).

Q8 reranker 가 있으면 k×rerank_multiplier(기본 3)를 받아 cross-encoder 로 다시 순위 매긴 상위 k 로
판정한다 (유사도 값은 그대로 — 임계치 판정용).

판정 후보는 과제형 자료원만(`candidates`, config/overlap.yaml candidates, ADR 0028): 저장소 검색을
자료원으로 걸러 받고(논문이 상위를 메워 사내 기록이 밀리지 않게), 논문·보고서·특허는 따로 검색해
`related_research`(관련 연구, 참고) 로 돌려준다. `__call__` 은 종전처럼 알림 목록만 — REST·MCP·
Streamlit·추천·차별화·측정이 그대로 쓴다. 관련 연구까지 필요한 진입점(REST ②)은 `run()`.
"""

from __future__ import annotations

import asyncio
from typing import Any

from rra.application.ports import DocumentRepository
from rra.domain.models import OverlapAlert, PrecheckResult, ProposalRequest
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.overlap import OwnUnit, judge
from rra.domain.rules.overlap_candidates import OverlapCandidateRule
from rra.domain.rules.retrieval_scope import overlap_candidates


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
        candidates: OverlapCandidateRule | None = None,
    ):
        self.repo, self.k, self.own, self.keywords = repo, k, own, keywords
        self.reranker, self.rerank_multiplier, self.mix = reranker, rerank_multiplier, mix
        self.candidates = candidates

    async def __call__(self, req: ProposalRequest) -> list[OverlapAlert]:
        return (await self.run(req)).alerts

    async def run(self, req: ProposalRequest) -> PrecheckResult:
        query = req.search_text()
        wide = self.k * self.rerank_multiplier if self.reranker is not None else self.k
        hits = self._filter(await self._search(query, wide))
        if self.reranker is not None:
            # 관련 연구 검색은 reranker(스레드) 와 겹쳐 돌린다 — 지연 상한 2초
            hits, research = await asyncio.gather(
                self.reranker.rerank_documents(query, hits, k=self.k), self._research(query)
            )
            hits = list(hits)
        else:
            hits = sorted(hits, key=lambda ds: -ds[1])[: self.k]
            research = await self._research(query)
        # judge 는 입력 순서(유사도 순 또는 reranker 순)를 차단 여부 안에서 유지한다
        alerts = judge(hits, own=self.own, query=query, keywords=self.keywords)
        return PrecheckResult(alerts=alerts, related_research=research)

    async def _search(self, query: str, k: int):
        rule = self.candidates
        if rule is None or not rule.restricts:
            return await self.repo.find_similar(query, k=k)
        sources = rule.project_sources()
        if rule.per_source <= 0:
            return await self.repo.find_similar(query, k=k, sources=sources)
        size = max(k, rule.pool_size)
        # 전체 검색을 먼저(질의 임베딩 한 번), 자료원별 검색은 그 뒤에 — 저장소가 같은 질의 임베딩을
        # 메모하므로 자료원 수만큼 임베딩하지 않는다.
        overall = await self.repo.find_similar(query, k=size, sources=sources)
        by_source = await asyncio.gather(
            *(self.repo.find_similar(query, k=rule.per_source, sources=[s]) for s in sources)
        )
        return rule.model_copy(update={"pool_size": size}).pool(
            dict(zip(sources, by_source, strict=True)), overall
        )

    def _filter(self, hits):
        hits = overlap_candidates(hits)
        if self.mix is not None:
            hits = self.mix.overlap_candidates(hits, lambda d: d.doc_type)
        if self.candidates is not None:
            hits = self.candidates.project_hits(hits)
        return hits

    async def _research(self, query: str):
        rule = self.candidates
        if rule is None or not rule.research or rule.research_k <= 0:
            return []
        hits = await self.repo.find_similar(
            query, k=rule.research_k * 2, sources=rule.research_sources()
        )
        return rule.related_research(hits)
