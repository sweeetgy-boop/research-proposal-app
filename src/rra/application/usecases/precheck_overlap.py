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

2026-10-28 밤 레인 A (ADR 0039) — 표 먼저:
- REST ② 는 `rule_stage(remember=True)` 로 규칙 판정 표를 먼저 돌려주고(메모에 "판정 전" 으로 남김),
  AI 같음 판정은 `judgment(req)` 가 따로 한다. 같은 입력의 판정이 이미 돌고 있으면 새로 부르지 않고
  그 작업을 기다린다(과제안 요청과 판정 요청이 같은 작업을 공유). 기다리는 쪽이 모두 취소되면 작업도
  취소한다 — 화면 [취소] 는 그 작업만 멈춘다.
- `current(req)` 는 지금 판정(진행 중이면 기다린 결과, 없으면 메모의 규칙 판정) — 과제안 근거용.

2026-11-09 레인 E (ADR 0059) — 기능 스위치 `switches`(모두 false 가 기본, false 면 아래는 전혀 돌지
않아
결과가 종전과 바이트 단위로 같다 — tests/application/test_overlap_switch_off.py):
- facets: 핵심어 뒤 `facet_split`(로컬 모델 → 규칙)로 4축을 나누고, 비어 있지 않은 축 2~4개를 각각
  저장소 검색(`find_similar` — 풀이 문서 단위라 청크 검색 대신 같은 문서 검색을 축마다 부른다)해
  RRF(k=60)로 합친 뒤 기존 풀 규칙(`candidates.pool`)로 이어 준다. 풀 크기·reranker 입력 수는 종전과
  같다.
  같음 판정에는 `facet_overlap` 을 요구한다(SameJudge.facets).
- idf_weighting: `idf`(말뭉치 IDF 표)를 judge 에 넘겨 핵심어 조건을 가중 합으로 본다.
- synonyms: 1단계에서는 검색 질의 확장만 가능(`expand_terms`) — 사람 검토 전에는 켜지 않는다.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from rra.application.ports import DocumentRepository
from rra.domain.models import OverlapAlert, PrecheckResult, ProposalRequest
from rra.domain.models.facets import Facets
from rra.domain.models.gap import JudgmentInfo, RelatedResearch
from rra.domain.rules.facets import facet_queries
from rra.domain.rules.fusion import reciprocal_rank_fusion
from rra.domain.rules.idf import IdfWeightingRule, IdfWeights
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.overlap import OwnUnit, RerankRule, judge
from rra.domain.rules.overlap_candidates import OverlapCandidateRule
from rra.domain.rules.overlap_switches import OFF, OverlapSwitches
from rra.domain.rules.retrieval_scope import overlap_candidates
from rra.domain.rules.series import (
    SeriesRule,
    group_hits,
    group_key,
    merge_series,
    pick_for_rerank,
)
from rra.domain.rules.similar_choice import merge_same_titles

logger = logging.getLogger("rra.precheck")
KeywordSource = Callable[[ProposalRequest], Awaitable[Any]]  # → LiveKeywords (ko·origin)
FacetSplit = Callable[
    [ProposalRequest, list[str] | None], Awaitable[Facets]
]  # usecases/facet_split
MEMO_MAX = 200
SERIES_FETCH_ROUNDS = 3
RRF_K = 60


@dataclass
class _Memo:
    at: float
    rule_alerts: list[OverlapAlert]  # AI 판정 전(규칙) — [다시 시도] 가 다시 판정한다
    result: PrecheckResult
    judged: bool = True  # False = 규칙 판정만(표 먼저 — AI 판정 전)


class JudgmentCancelled(Exception):
    """같은 입력의 AI 판정 작업이 (다른 요청의 [취소]로) 멈췄다."""


@dataclass
class _Inflight:
    task: asyncio.Task
    waiters: int = 0


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
        series: SeriesRule | None = None,  # 같은 연작 한 줄 (ADR 0043) — None 이면 같은 제목만
        same_judge: Any | None = None,  # SameJudge (usecases/judge_sameness)
        keyword_source: KeywordSource | None = None,
        memo_ttl: float = 1800.0,
        clock: Callable[[], float] = time.monotonic,
        switches: OverlapSwitches | None = None,  # ADR 0059 — None·모두 false 면 종전과 같다
        facet_split: FacetSplit | None = None,  # 4축 분해 (facets 스위치일 때만 호출)
        idf: IdfWeights | None = None,  # 말뭉치 IDF 표 (idf_weighting 스위치일 때만 쓴다)
        idf_rule: IdfWeightingRule | None = None,
    ):
        self.repo, self.k, self.own, self.keywords = repo, k, own, keywords
        self.switches = switches or OFF
        self.facet_split = facet_split
        self.idf, self.idf_rule = idf, idf_rule
        self.reranker, self.rerank_multiplier, self.mix = reranker, rerank_multiplier, mix
        self.candidates = candidates
        self.rerank = rerank
        self.series = series if series is not None and series.enabled else None
        self.same_judge = same_judge
        self.keyword_source = keyword_source
        self.memo_ttl = memo_ttl
        self._clock = clock
        self._memo: OrderedDict[str, _Memo] = OrderedDict()
        self._inflight: dict[str, _Inflight] = {}

    async def __call__(self, req: ProposalRequest) -> list[OverlapAlert]:
        memo = self._get(req)
        if memo is not None:
            return list(memo.result.alerts)
        return (await self.run(req, ai=False)).alerts

    def memo(self, req: ProposalRequest) -> PrecheckResult | None:
        """같은 입력의 최근 판정(있으면). 선택 기록·후속 화면이 점수·판정을 다시 계산하지 않게."""
        m = self._get(req)
        return m.result if m is not None else None

    async def search_research(self, req: ProposalRequest) -> list[RelatedResearch]:
        """② 관련 연구 검색만 다시 — 메모가 없을 때 비교표 참고 논문 열의 관련 순위용(같은 질의·
        같은 자료원·같은 점수)."""
        return list(await self._research(req.search_text()))

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
        research: bool = True,
        remember: bool = False,
    ) -> PrecheckResult:
        """규칙 판정까지(AI 판정 전). keywords=True 이고 핵심어가 없으면 keyword_source(Argon
        키워드)를 부른다. research=False 면 관련 연구 검색을 건너뛴다(과제안 겹침 확인).
        remember=True 면 "판정 전" 메모로 남겨 뒤의 `judgment` 가 검색을 다시 하지
        않는다(표 먼저, ADR 0039)."""
        query = req.search_text()
        if keywords and core_keywords is None and self.keyword_source is not None:
            found = await self._keywords(req)
            if found is not None:
                core_keywords, keyword_origin = list(found.ko), str(found.origin)
        wide = self.k * self.rerank_multiplier if self.reranker is not None else self.k
        facets = await self._facets(req, core_keywords)  # 스위치 off 면 None (호출 없음)
        if self.series is not None:
            alerts, related, pool = await self._series_alerts(
                query, wide, core_keywords=core_keywords, research=research, facets=facets
            )
            rows = merge_series(alerts, pool=pool)[: self.k]
        else:
            hits = self._filter(await self._search(query, wide, facets=facets))
            scores: dict[str, float] | None = None
            if self.reranker is not None:
                # 관련 연구 검색은 reranker(스레드) 와 겹쳐 돌린다 — 지연 상한 2초
                (hits, scores), related = await asyncio.gather(
                    self._rerank(query, hits), self._research(query) if research else _nothing()
                )
            else:
                hits = sorted(hits, key=lambda ds: -ds[1])[: self.k]
                related = await self._research(query) if research else []
            # judge 는 입력 순서(유사도 순 또는 reranker 순)를 차단 여부 안에서 유지한다
            alerts = self._judge(hits, query, scores, core_keywords)
            rows = merge_same_titles(alerts)
        result = PrecheckResult(
            alerts=rows,
            related_research=related,
            judgment=JudgmentInfo(status="off"),
            core_keywords=list(core_keywords or []),
            keyword_origin=keyword_origin or "rule",
        )
        if facets is not None:
            result = result.model_copy(update={"facets": facets})
        if remember:
            memo = self._get(req)
            if memo is None or not memo.judged:  # 이미 AI 판정한 같은 입력은 덮어쓰지 않는다
                self._put(req, _Memo(self._clock(), list(result.alerts), result, judged=False))
        return result

    async def judge_stage(self, req: ProposalRequest, rule: PrecheckResult) -> PrecheckResult:
        """규칙 판정 결과에 AI 같음 판정을 붙이고 메모한다 (같은 입력의 후속 화면이 다시 쓴다)."""
        result = rule
        if self.same_judge is not None:
            alerts, info = await self.same_judge(req, list(rule.alerts))
            result = rule.model_copy(update={"alerts": alerts, "judgment": info})
        self._put(req, _Memo(self._clock(), list(rule.alerts), result))
        return result

    async def judgment(self, req: ProposalRequest, *, retry: bool = False) -> PrecheckResult:
        """AI 같음 판정(표 먼저 뒤). 같은 입력의 AI 판정 메모가 있으면 그것(retry=False), 진행 중인
        판정이 있으면 그 작업을 기다린다. 메모가 없으면 전체(검색부터). 앱 제한 시간 없음 — 기다리는
        쪽(화면 요청)이 모두 취소되면 작업도 취소된다."""
        memo = self._get(req)
        if (
            not retry
            and memo is not None
            and memo.judged
            and memo.result.judgment.status in ("ai", "no_candidates", "off")
        ):
            return memo.result
        return await self._join(req, lambda: self.rejudge(req))

    async def current(self, req: ProposalRequest) -> PrecheckResult | None:
        """지금 판정 — 판정 전 메모면 AI 판정을 시작(또는 진행 중인 작업에 합류)해 기다린
        결과, 판정이 끝난 메모면 그것, 메모가 없으면 None. 과제안(추천)이 AI 판정을
        근거로 쓰게 한다 — 과제안 요청이 판정 요청보다 먼저 와도 판정은 한 번만 돈다."""
        memo = self._get(req)
        if memo is None:
            return None
        if self.same_judge is None or (memo.judged and self._key(req) not in self._inflight):
            return memo.result
        try:
            return await self._join(req, lambda: self.rejudge(req))
        except JudgmentCancelled:  # 판정을 화면이 취소 — 과제안은 규칙 판정으로
            logger.info("precheck.judgment_cancelled")
        except Exception as exc:  # 판정 작업 실패는 과제안을 막지 않는다 — 메모(규칙)로
            logger.warning("precheck.judgment_failed err=%s", type(exc).__name__)
        latest = self._get(req) or memo
        return latest.result

    async def _join(self, req: ProposalRequest, start: Callable[[], Awaitable[PrecheckResult]]):
        key = self._key(req)
        entry = self._inflight.get(key)
        if entry is None or entry.task.done():
            task = asyncio.ensure_future(start())
            entry = _Inflight(task)
            self._inflight[key] = entry

            def _clear(_t: asyncio.Task, key: str = key, entry: _Inflight = entry) -> None:
                if self._inflight.get(key) is entry:
                    self._inflight.pop(key, None)
                if not _t.cancelled():
                    _t.exception()  # 결과를 아무도 안 읽어도 경고가 남지 않게

            task.add_done_callback(_clear)
        entry.waiters += 1
        try:
            return await asyncio.shield(entry.task)
        except asyncio.CancelledError:
            me = asyncio.current_task()
            if me is not None and me.cancelling() == 0 and entry.task.cancelled():
                raise JudgmentCancelled from None  # 다른 화면의 [취소]로 작업이 멈췄다
            if not entry.task.done() and entry.waiters <= 1:
                entry.task.cancel()  # 기다리는 화면이 없으면 작업도 멈춘다 ([취소])
            raise
        finally:
            entry.waiters -= 1

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

    def _judge(self, hits, query: str, scores, core_keywords) -> list[OverlapAlert]:
        """규칙 판정 — idf 스위치가 켜졌을 때만 IDF 표를 넘긴다(아니면 종전 호출과 같다)."""
        extra: dict[str, Any] = {}
        if self.switches.idf_weighting and self.idf is not None:
            extra = {"idf": self.idf, "idf_rule": self.idf_rule}
        return judge(
            hits,
            own=self.own,
            query=query,
            keywords=self.keywords,
            scores=scores,
            rerank=self.rerank if scores is not None else None,
            core_keywords=core_keywords,
            **extra,
        )

    async def _facets(self, req: ProposalRequest, core_keywords: list[str] | None) -> Facets | None:
        """4축 분해 (ADR 0059) — facets 스위치가 켜져 있고 분해기가 있을 때만. 실패는 None(한
        질의)."""
        if not self.switches.facets or self.facet_split is None:
            return None
        try:
            return await self.facet_split(req, core_keywords)
        except Exception as exc:  # 분해 실패는 ② 를 막지 않는다 — 종전 한 질의 검색
            logger.warning("precheck.facet_split_failed err=%s", type(exc).__name__)
            return None

    async def _series_alerts(
        self,
        query: str,
        wide: int,
        *,
        core_keywords: list[str] | None,
        research: bool,
        facets: Facets | None = None,
    ):
        """연작 묶기(ADR 0043) — 후보를 fetch_multiplier 배로 넓게 받아 서로 다른 묶음 wide 개까지
        풀을 만들고, 묶음마다 e5 상위 rerank_per_series 건만 reranker 에 보낸다(비용은 종전과 같은
        wide 건). 판정 행 + 관련 연구 + 풀(구성원 붙이기용)."""
        rule = self.series or SeriesRule()
        fetch = rule.fetch_multiplier
        pool: list = []
        for _ in range(SERIES_FETCH_ROUNDS):  # 묶은 뒤 k 줄이 안 되면 더 넓게 (최대 2번)
            wider = self._filter(
                await self._search(
                    query,
                    wide,
                    fetch=fetch,
                    group=lambda d: group_key(d.title),
                    facets=facets,
                )
            )
            grew = len(wider) > len(pool)
            pool = wider
            groups = group_hits(pool)
            if len(groups) >= self.k or not grew:
                break
            fetch *= 2
        if len(groups) > wide:  # 묶음 수 상한 (제한 없는 검색 경로)
            groups = type(groups)(list(groups.items())[:wide])
            pool = [m for members in groups.values() for m in members]
        if self.reranker is not None:
            limit = rule.rerank_max or wide
            ranked = pick_for_rerank(groups, rule.rerank_per_series, limit)
            (hits, scores), related = await asyncio.gather(
                self._rerank(query, ranked, keep=len(ranked)),
                self._research(query) if research else _nothing(),
            )
        else:
            hits = sorted(
                pick_for_rerank(groups, rule.rerank_per_series, len(pool)), key=lambda ds: -ds[1]
            )
            scores = None
            related = await self._research(query) if research else []
        alerts = self._judge(hits, query, scores, core_keywords)
        return alerts, related, pool

    async def _rerank(self, query: str, hits, *, keep: int | None = None):
        """(상위 keep(기본 k), doc_id → 점수 또는 None). 점수를 주는 어댑터면 점수 순, 아니면
        순서만."""
        top = self.k if keep is None else keep
        scorer = getattr(self.reranker, "score_documents", None)
        if scorer is None:
            return list(await self.reranker.rerank_documents(query, hits, k=top)), None
        if not hits:
            return [], {}
        values = list(await scorer(query, hits))
        order = sorted(range(len(hits)), key=lambda i: -values[i])[:top]
        return [hits[i] for i in order], {hits[i][0].doc_id: float(values[i]) for i in order}

    async def _search(
        self, query: str, k: int, *, fetch: int = 1, group=None, facets: Facets | None = None
    ):
        """판정 후보 풀. fetch>1·group(연작 묶기, ADR 0043)이면 저장소에서 fetch 배로 받아 서로 다른
        묶음 k 개(자료원별 per_source 묶음)까지 — 같은 묶음의 다른 판은 구성원으로 붙는다.
        facets(ADR 0059, 스위치 facets 일 때만 값이 온다)가 있으면 축별 질의로 같은 검색을 각각 하고
        RRF 로 합친 목록을 종전 검색 자리에 쓴다 — 풀 크기는 같다."""
        rule = self.candidates
        queries = facet_queries(facets)
        find = self._fused_find if queries else self._plain_find
        if rule is None or not rule.restricts:
            return await find(queries or [query], k=k * fetch)
        sources = rule.project_sources()
        if rule.per_source <= 0:
            return await find(queries or [query], k=k * fetch, sources=sources)
        size = max(k, rule.pool_size)
        # 전체 검색을 먼저(질의 임베딩 한 번), 자료원별 검색은 그 뒤에 — 저장소가 같은 질의 임베딩을
        # 메모하므로 자료원 수만큼 임베딩하지 않는다.
        overall = await find(queries or [query], k=size * fetch, sources=sources)
        by_source = await asyncio.gather(
            *(find(queries or [query], k=rule.per_source * fetch, sources=[s]) for s in sources)
        )
        return rule.model_copy(update={"pool_size": size}).pool(
            dict(zip(sources, by_source, strict=True)),
            overall,
            group=group,
        )

    async def _plain_find(self, queries: list[str], *, k: int, sources: list[str] | None = None):
        """종전 한 질의 검색 — 호출 모양(find_similar 인자)을 그대로 둔다."""
        if sources is None:
            return await self.repo.find_similar(queries[0], k=k)
        return await self.repo.find_similar(queries[0], k=k, sources=sources)

    async def _fused_find(self, queries: list[str], *, k: int, sources: list[str] | None = None):
        """축별 질의 검색 → RRF(k=60) 합침 (ADR 0059). 결과 수는 k 로 같고, 유사도는 그 문서가 어느
        축에서든 받은 최고 e5 값(표시용 — 차단은 reranker·핵심어가 정한다)."""
        kw: dict[str, Any] = {"k": k}
        if sources is not None:
            kw["sources"] = sources
        results = await asyncio.gather(*(self.repo.find_similar(q, **kw) for q in queries))
        docs: dict[str, Any] = {}
        best: dict[str, float] = {}
        for hits in results:
            for doc, sim in hits:
                docs.setdefault(doc.doc_id, doc)
                best[doc.doc_id] = max(best.get(doc.doc_id, 0.0), float(sim))
        fused = reciprocal_rank_fusion(
            [[doc.doc_id for doc, _ in hits] for hits in results], k=RRF_K
        )
        return [(docs[i], best[i]) for i, _ in fused[:k]]

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


async def _nothing() -> list:
    return []
