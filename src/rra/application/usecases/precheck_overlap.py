"""② 유사과제 사전 확인 — find_similar(k) → 판정(domain/rules/overlap.judge).

Q8 reranker 가 있으면 k×rerank_multiplier(기본 3)를 받아 cross-encoder 로 다시 순위 매긴 상위 k 로
판정한다. reranker 가 점수를 주면(`score_documents`) 그 점수가 차단 판단의 주 점수다(2026-10-28 레인
A — e5 유사도는 철도 문서끼리 0.85~0.86 에 몰려 가르지 못한다). e5 유사도는 후보 검색·표시용.

판정 후보는 과제형 자료원만(`candidates`, config/overlap.yaml candidates, ADR 0028): 저장소 검색을
자료원으로 걸러 받고(논문이 상위를 메워 사내 기록이 밀리지 않게), 논문·보고서·특허는 따로 검색해
`related_research`(관련 연구, 참고) 로 돌려준다.

2026-10-28 레인 A ② 판정 정확도:
- 공유 키워드는 아이디어 핵심어(Argon 키워드 — 실시간 검색과 같은 키워드, 없으면 규칙 키워드) 중
  문서에 있는 것만 센다 (`core_keywords`).
- 제목이 같은 행(NTIS 번호만 다른 중복)은 한 행으로 합친다 (similar_choice.merge_same_titles).
- `same_judge`(AI 같음 판정, Argon → 로컬 → 규칙)가 있으면 상위 10건을 판정해 same 만 차단.
- 결과는 입력 글(search_text) 해시로 메모한다(기본 30분). `__call__`(REST 후속 경로·MCP·추천·측정)은
  메모가 있으면 그 결과를, 없으면 AI 판정 없이 규칙 판정만 돌린다 — 추천의 자기 중복 검사가 추천마다
  외부 LLM 을 부르지 않게.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from rra.application.ports import DocumentRepository
from rra.domain.models import OverlapAlert, PrecheckResult, ProposalRequest
from rra.domain.models.gap import JudgmentInfo
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.overlap import OwnUnit, RerankRule, judge
from rra.domain.rules.overlap_candidates import OverlapCandidateRule
from rra.domain.rules.retrieval_scope import overlap_candidates
from rra.domain.rules.similar_choice import merge_same_titles

KeywordSource = Callable[[ProposalRequest], Awaitable[Any]]  # → LiveKeywords (ko·origin)
MEMO_MAX = 200


@dataclass
class _Memo:
    at: float
    rule_alerts: list[OverlapAlert]  # AI 판정 전(규칙) — [다시 시도] 가 다시 판정한다
    result: PrecheckResult


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
        rerank: RerankRule | None = None,
        same_judge: Any | None = None,  # SameJudge (usecases/judge_sameness)
        keyword_source: KeywordSource | None = None,
        memo_ttl: float = 1800.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.repo, self.k, self.own, self.keywords = repo, k, own, keywords
        self.reranker, self.rerank_multiplier, self.mix = reranker, rerank_multiplier, mix
        self.candidates = candidates
        self.rerank = rerank
        self.same_judge = same_judge
        self.keyword_source = keyword_source
        self.memo_ttl = memo_ttl
        self._clock = clock
        self._memo: OrderedDict[str, _Memo] = OrderedDict()

    async def __call__(self, req: ProposalRequest) -> list[OverlapAlert]:
        memo = self._get(req)
        if memo is not None:
            return list(memo.result.alerts)
        return (await self.run(req, ai=False)).alerts

    def memo(self, req: ProposalRequest) -> PrecheckResult | None:
        """같은 입력의 최근 판정(있으면). 선택 기록·후속 화면이 점수·판정을 다시 계산하지 않게."""
        m = self._get(req)
        return m.result if m is not None else None

    async def run(
        self,
        req: ProposalRequest,
        *,
        ai: bool = True,
        core_keywords: list[str] | None = None,
        keyword_origin: str | None = None,
    ) -> PrecheckResult:
        """검색 → (reranker) → 규칙 판정 → 같은 제목 합치기 → (AI 같음 판정). ai=False 면 규칙만."""
        rule = await self.rule_stage(
            req, core_keywords=core_keywords, keyword_origin=keyword_origin, keywords=ai
        )
        if not ai:
            return rule
        return await self.judge_stage(req, rule)

    async def rule_stage(
        self,
        req: ProposalRequest,
        *,
        core_keywords: list[str] | None = None,
        keyword_origin: str | None = None,
        keywords: bool = True,
    ) -> PrecheckResult:
        """규칙 판정까지(AI 판정 전). REST ② 는 이 결과로 과제 추천을 AI 판정과 동시에 돌린다.
        keywords=True 이고 핵심어가 없으면 keyword_source(Argon 키워드)를 부른다."""
        query = req.search_text()
        if keywords and core_keywords is None and self.keyword_source is not None:
            found = await self._keywords(req)
            if found is not None:
                core_keywords, keyword_origin = list(found.ko), str(found.origin)
        wide = self.k * self.rerank_multiplier if self.reranker is not None else self.k
        hits = self._filter(await self._search(query, wide))
        scores: dict[str, float] | None = None
        if self.reranker is not None:
            # 관련 연구 검색은 reranker(스레드) 와 겹쳐 돌린다 — 지연 상한 2초
            (hits, scores), research = await asyncio.gather(
                self._rerank(query, hits), self._research(query)
            )
        else:
            hits = sorted(hits, key=lambda ds: -ds[1])[: self.k]
            research = await self._research(query)
        # judge 는 입력 순서(유사도 순 또는 reranker 순)를 차단 여부 안에서 유지한다
        alerts = judge(
            hits,
            own=self.own,
            query=query,
            keywords=self.keywords,
            scores=scores,
            rerank=self.rerank if scores is not None else None,
            core_keywords=core_keywords,
        )
        return PrecheckResult(
            alerts=merge_same_titles(alerts),
            related_research=research,
            judgment=JudgmentInfo(status="off"),
            core_keywords=list(core_keywords or []),
            keyword_origin=keyword_origin or "rule",
        )

    async def judge_stage(self, req: ProposalRequest, rule: PrecheckResult) -> PrecheckResult:
        """규칙 판정 결과에 AI 같음 판정을 붙이고 메모한다 (같은 입력의 후속 화면이 다시 쓴다)."""
        result = rule
        if self.same_judge is not None:
            alerts, info = await self.same_judge(req, list(rule.alerts))
            result = rule.model_copy(update={"alerts": alerts, "judgment": info})
        self._put(req, _Memo(self._clock(), list(rule.alerts), result))
        return result

    async def rejudge(self, req: ProposalRequest) -> PrecheckResult:
        """[다시 시도] — 규칙 판정(메모)은 그대로 두고 AI 같음 판정만 다시. 메모가 없으면 전체."""
        memo = self._get(req)
        if memo is None or self.same_judge is None:
            return await self.run(req)
        alerts, info = await self.same_judge(req, list(memo.rule_alerts))
        result = memo.result.model_copy(update={"alerts": alerts, "judgment": info})
        self._put(req, _Memo(self._clock(), memo.rule_alerts, result))
        return result

    # ── 메모 ─────────────────────────────────────────────
    @staticmethod
    def _key(req: ProposalRequest) -> str:
        return hashlib.sha256(req.search_text().encode("utf-8")).hexdigest()

    def _get(self, req: ProposalRequest) -> _Memo | None:
        key = self._key(req)
        m = self._memo.get(key)
        if m is None:
            return None
        if self._clock() - m.at > self.memo_ttl:
            self._memo.pop(key, None)
            return None
        return m

    def _put(self, req: ProposalRequest, memo: _Memo) -> None:
        key = self._key(req)
        self._memo[key] = memo
        self._memo.move_to_end(key)
        while len(self._memo) > MEMO_MAX:
            self._memo.popitem(last=False)

    # ── 검색·순위 ────────────────────────────────────────
    async def _keywords(self, req: ProposalRequest):
        try:
            return await self.keyword_source(req)  # type: ignore[misc]
        except Exception:  # 키워드 실패는 판정을 막지 않는다 — 질의 키워드로
            return None

    async def _rerank(self, query: str, hits):
        """(상위 k, doc_id → 점수 또는 None). 점수를 주는 어댑터면 점수 순, 아니면 순서만."""
        scorer = getattr(self.reranker, "score_documents", None)
        if scorer is None:
            return list(await self.reranker.rerank_documents(query, hits, k=self.k)), None
        if not hits:
            return [], {}
        values = list(await scorer(query, hits))
        order = sorted(range(len(hits)), key=lambda i: -values[i])[: self.k]
        return [hits[i] for i in order], {hits[i][0].doc_id: float(values[i]) for i in order}

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
