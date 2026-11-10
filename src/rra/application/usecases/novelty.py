"""새 과제 추천 갈래의 협력자 — 새로움 확인(`WideNoveltyCheck`)·유추 검색
(`ProblemAnalogySearch`) (ADR 0057, 계약 docs/contracts/novel-recommend.md 2·3.1·3.2·7절).

새로움 확인 — novel 판정 뒤 실시간 검색 범위를 넓혀 한 번 더 본다:
1. 넓힌 설정(config/novelty.yaml `novelty.live`: 질의 수·자료원당 상한·대기 시간)의
   실시간 검색 인스턴스(`LiveSearch`, ADR 0031 — 저장·중복 정리·IP 거부 기록·캐시 그대로)로
   ScienceON·NTIS·OpenAlex 를 다시 검색한다. NTIS 가 최근 IP 거부로 기록돼 있으면
   LiveSearch 가 호출하지 않고 ip_blocked 로 둔다.
2. 새로 받은 자료가 있으면 ② 와 같은 규칙 판정(주입받는 `rule_check` — 보통
   PrecheckOverlap.rule_stage, 후보 자료원·차단 기준 그대로)을 다시 돌려 원래 알림에 없던
   규칙 차단 행을 `new_alerts` 로 돌려준다.
3. coverage 에는 실제로 확인한 자료원만 — 저장 자료 판정 후보 자료원 중 문서가 있는 것 +
   실시간 응답이 온 자료원. 응답 못 받은 자료원은 unavailable(ip_blocked·timeout·error·
   off·no_key).

유추 검색 — 아이디어의 '문제' 축(장소·시설·철도 단어 제거, domain/rules/novelty)으로
저장 자료 + 실시간 검색을 하고, 같은 분야(철도) 자료를 빼고 관련도 하한(evidence_floor
0.79) 이상인 다른 분야 자료 최대 5건. 분야 이름·이유는 규칙(메타데이터·공유 문제어)으로만.

둘 다 같은 입력이면 프로세스 안 LRU 로 재사용한다(세션 안). 실패는 추천을 막지 않는다 —
실시간 검색이 안 되면 저장 자료만(live=false). 공용 계정 인스턴스(include_internal=False)는
internal 문서를 analogies·new_alerts 에서 뺀다. 수집 텍스트는 비신뢰(A) — 제목은 그대로
담고 화면이 정리한다. 로그에는 건수·상태·예외 클래스명만(D).

문제 정의 카드(ADR 0065, 계약 problem-card.md 4·4.1절) — 요청에 카드가 있고
`problem_card.yaml` 의 `use.analogy_queries` 가 켜져 있을 때만 유추 검색이 카드로 돈다:
질의는 `domain/rules/card_queries.card_queries` 한 곳(저장 자료 = 사다리 3단 + 국문·영문 기능 문장,
실시간 = 국문·영문 → OpenAlex 가 영문 질의를 받는다, 확인된 IPC → KIPRIS 분류 검색),
실시간 세션 소유자·결과 메모 키는 **실제로 보낸 질의의 지문**으로 가른다. `use.analogy_rank` 면
최종 5건을 `domain/rules/analogy_rank`(대상어 겹침 → 기능 문장 재순위 → 자료원당 상한)로 고른다.
카드가 없거나 꺼져 있으면 아래 종전 경로가 그대로 돈다. 새로움 확인은 카드를 쓰지 않는다.
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from rra.application.ports import DocumentRepository, EmbeddingPort
from rra.application.ports.reranker import DocumentScorerPort
from rra.application.usecases.live_search import NOTICE_NO_KEYWORDS, NOTICE_NO_SOURCE
from rra.application.usecases.novel_contract import NoveltyOutcome
from rra.domain.models import Document, OverlapAlert, ProposalRequest
from rra.domain.models.live_search import LIVE_SOURCES, LiveKeywords, LiveSearchSummary
from rra.domain.models.novel import (
    ANALOGY_OTHER_FIELD,
    ANALOGY_RELATED,
    MAX_ANALOGIES,
    Analogy,
    AnalogyMember,
    AnalogyReport,
    NoveltyCoverage,
)
from rra.domain.models.problem_card import ProblemCard, ProblemCardConfig
from rra.domain.rules.analogy_group import Grouped, dot_matrix, group_similar
from rra.domain.rules.analogy_rank import (
    RankRow,
    card_shared_terms,
    cut_weak,
    drop_similar_titles,
    few_analogies,
    object_terms,
    order_rows,
    rank_rows,
    take_by_source,
)
from rra.domain.rules.card_queries import (
    CardQueries,
    analogy_owner,
    card_queries,
    class_query,
    memo_groups,
    pick_fingerprint,
    rerank_query,
)
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.live_search import keyword_cache_key, normalized_title, rule_keywords
from rra.domain.rules.novelty import (
    AnalogySettings,
    NoveltySettings,
    RailFieldRule,
    domain_label,
    en_terms,
    input_key,
    pick_new_alerts,
    problem_phrases_en,
    problem_phrases_ko,
    problem_query,
    problem_terms,
    rail_asset_basis,
    rail_reason,
    shared_terms,
    why_relevant,
)
from rra.domain.rules.overlap import OVERLAP_SOURCES, SOURCE_LABELS
from rra.domain.rules.relevance import RelevanceFloor, has_hangul

logger = logging.getLogger("rra.novelty")

NOTE_STORED_ONLY = "저장 자료 범위 안에서 기존 과제 없음"
NOVELTY_OWNER = "novelty"
ANALOGY_OWNER = "analogy"
GROUP_EMBED_CHARS = 1500  # 묶기용 초록 임베딩에 넣는 글자 수

RuleCheck = Callable[[ProposalRequest, list[str] | None], Awaitable[Sequence[OverlapAlert]]]
KeywordSource = Callable[[ProposalRequest], Awaitable[LiveKeywords]]


@runtime_checkable
class LiveSearchLike(Protocol):
    """LiveSearch(usecases/live_search) 중 여기서 쓰는 부분."""

    @property
    def enabled(self) -> bool: ...

    async def prepare(self, owner: str, req: ProposalRequest) -> LiveSearchSummary: ...


def precheck_rule_check(precheck: Any) -> RuleCheck:
    """PrecheckOverlap → rule_check. ② 의 규칙 판정(검색 → reranker → 규칙 → 같은 제목·연작
    합치기)만, 관련 연구 검색·AI 같음 판정·메모 없이."""

    async def check(req: ProposalRequest, core: list[str] | None) -> Sequence[OverlapAlert]:
        result = await precheck.rule_stage(req, core_keywords=core, research=False)
        return list(result.alerts)

    return check


class _Memo:
    """프로세스 안 LRU (+ 보관 시간)."""

    def __init__(self, size: int, ttl_seconds: float, clock: Callable[[], float]):
        self.size, self.ttl, self._clock = size, ttl_seconds, clock
        self._items: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        item = self._items.get(key)
        if item is None:
            return None
        if self._clock() - item[0] > self.ttl:
            self._items.pop(key, None)
            return None
        self._items.move_to_end(key)
        return item[1]

    def put(self, key: str, value: Any) -> None:
        self._items[key] = (self._clock(), value)
        self._items.move_to_end(key)
        while len(self._items) > self.size:
            self._items.popitem(last=False)


async def _prepare(live: LiveSearchLike | None, owner: str, req: ProposalRequest, tag: str):
    """실시간 검색(시작 또는 이어 쓰기 + 기다리기). 꺼짐·실패면 None."""
    if live is None or not live.enabled:
        return None
    try:
        return await live.prepare(owner, req)
    except Exception as exc:  # 실시간 검색 실패는 저장 자료만으로 계속
        logger.warning("%s.live_failed err=%s", tag, type(exc).__name__)
        return None


def _has_fresh(summary: LiveSearchSummary) -> bool:
    """넓힌 검색이 DB 에 새로 저장한 문서가 있는가(LiveSourceResult.new). 캐시·기존 문서뿐이면
    ② 판정이 이미 본 범위라 다시 판정하지 않는다."""
    return any(r.new > 0 for r in summary.sources)


def _unavailable_status(status: str, notice: str | None) -> str | None:
    """LiveSourceResult → coverage.unavailable 열거값. 응답이 왔으면(ok) None."""
    if status == "ok":
        return "off" if notice == NOTICE_NO_KEYWORDS else None  # 검색어가 없어 보내지 않음
    if status == "error" and notice == NOTICE_NO_SOURCE:
        return "no_key"
    if status in ("ip_blocked", "timeout", "error", "off", "rate_limited"):
        return status
    return "error"


def build_coverage(
    stored: Sequence[str], summary: LiveSearchSummary | None, *, live_sources: Sequence[str]
) -> NoveltyCoverage:
    """확인 범위 — 실제로 확인한 자료원만. stored: 저장 자료 검색에 쓴(문서가 있는) 자료원.
    summary 가 None 이면(꺼짐·조립 안 됨·실패) 실시간 자료원은 모두 off."""
    searched: list[str] = [s for s in dict.fromkeys(stored)]
    unavailable: list[dict[str, str]] = []
    live = False
    results = {r.source: r for r in (summary.sources if summary is not None else [])}
    for name in live_sources:
        r = results.get(name)
        if summary is None or summary.status == "off":
            status: str | None = "off"
        elif r is None or summary.status == "pending":
            # 기다리는 동안 끝나지 않음 — 받은 자료도 아직 저장·판정 전이라 확인한 것으로
            # 보지 않는다
            status = "timeout"
        else:
            status = _unavailable_status(r.status, r.notice)
        if status is None:
            live = True
            if name not in searched:
                searched.append(name)
        else:
            unavailable.append({"source": name, "status": status})
    order = list(SOURCE_LABELS)
    searched.sort(key=lambda s: order.index(s) if s in order else len(order))
    return NoveltyCoverage(
        searched=searched,
        searched_labels=[SOURCE_LABELS.get(s, s) for s in searched],
        live=live,
        unavailable=unavailable,
        note=NoveltyCoverage().note if live else NOTE_STORED_ONLY,
    )


async def _visible(repo: DocumentRepository, doc_id: str, include_internal: bool) -> bool:
    if include_internal:
        return True
    try:
        doc = await repo.get_document(doc_id)
    except Exception as exc:
        logger.info("novelty.lookup_failed err=%s", type(exc).__name__)
        return False
    return doc is not None and doc.visibility != "internal"


# ── 새로움 확인 ────────────────────────────────────────────
class WideNoveltyCheck:
    """`novel_contract.NoveltyCheck` 구현.

    live: 넓힌 설정의 LiveSearch(config/novelty.yaml novelty.live →
      `LiveWidening.live_config`). None 이면 저장 자료만(live=false).
    rule_check: ② 규칙 판정(`precheck_rule_check(precheck)`).
    stored_sources: 저장 자료 판정 후보 자료원(overlap.yaml candidates.project 의 자료원). 비면 판정
      자료원 전부(OVERLAP_SOURCES). 문서가 한 건도 없는 자료원은 coverage 에 넣지 않는다.
    """

    def __init__(
        self,
        repo: DocumentRepository,
        *,
        rule_check: RuleCheck,
        live: LiveSearchLike | None = None,
        settings: NoveltySettings | None = None,
        stored_sources: Sequence[str] = (),
        live_sources: Sequence[str] = LIVE_SOURCES,
        include_internal: bool = True,
        memo_size: int = 64,
        memo_minutes: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.repo = repo
        self.rule_check = rule_check
        self.settings = settings or NoveltySettings()
        self.live = live if self.settings.enabled else None
        self.stored_sources = list(stored_sources) or list(OVERLAP_SOURCES)
        self.live_sources = list(live_sources)
        self.include_internal = include_internal
        self._memo = _Memo(memo_size, memo_minutes * 60, clock)

    async def __call__(
        self,
        req: ProposalRequest,
        alerts: list[OverlapAlert],
        *,
        core_keywords: list[str] | None = None,
    ) -> NoveltyOutcome:
        alert_ids = sorted({a.doc_id for a in alerts} | {m for a in alerts for m in a.merged_ids})
        key = input_key(req, core_keywords or [], alert_ids)
        cached = self._memo.get(key)
        if cached is not None:
            return cached
        summary = await _prepare(self.live, NOVELTY_OWNER, req, "novelty")
        new_alerts: list[OverlapAlert] = []
        if summary is not None and summary.doc_ids and _has_fresh(summary):
            # 규칙 판정(검색 → reranker)은 DB 에 새로 들어온 문서가 있을 때만 — 이미 있던 문서는
            # ② 가 같은 검색으로 이미 보았다(2026-11-09 레인 A, 응답 시간)
            try:
                rows = await self.rule_check(req, list(core_keywords) if core_keywords else None)
            except Exception as exc:  # 판정 실패는 novel 을 막지 않는다 — 되돌림 없음
                logger.warning("novelty.rule_check_failed err=%s", type(exc).__name__)
                rows = []
            for a in pick_new_alerts(rows, alerts):
                if await _visible(self.repo, a.doc_id, self.include_internal):
                    new_alerts.append(a)
        coverage = build_coverage(await self._stored(), summary, live_sources=self.live_sources)
        outcome = NoveltyOutcome(coverage=coverage, new_alerts=new_alerts)
        logger.info(
            "novelty.done live=%s searched=%d unavailable=%d new_alerts=%d",
            coverage.live,
            len(coverage.searched),
            len(coverage.unavailable),
            len(new_alerts),
        )
        if summary is None or summary.status != "pending":  # 못 끝난 검색은 다음에 다시
            self._memo.put(key, outcome)
        return outcome

    async def _stored(self) -> list[str]:
        try:
            counts = await self.repo.count_by_source()
        except Exception as exc:  # 셀 수 없으면 검색한 자료원 목록 그대로
            logger.info("novelty.count_failed err=%s", type(exc).__name__)
            return list(self.stored_sources)
        return [s for s in self.stored_sources if counts.get(s)]


# ── 유추 검색 ──────────────────────────────────────────────
def queries_for(req: ProposalRequest, config: ProblemCardConfig | None) -> CardQueries | None:
    """카드 → 질의 묶음(0단계 모듈 한 곳). 카드가 없거나 `use.analogy_queries` 가 꺼져 있으면
    None."""
    card = getattr(req, "problem_card", None)
    if config is None or card is None:
        return None
    return card_queries(
        card,
        use_queries=config.uses("analogy_queries"),
        use_class=config.uses("kipris_class"),
    )


class ProblemKeywords:
    """유추 검색용 LiveSearch 의 키워드 — ProblemAnalogySearch 가 입력마다 '문제' 축 질의를
    넣어 두면 LiveSearch 가 그것으로 검색한다. 넣어 둔 것이 없으면 규칙 기반 문제어(LLM 없음)."""

    def __init__(
        self,
        rule: KeywordRule | None = None,
        settings: AnalogySettings | None = None,
        *,
        card_config: ProblemCardConfig | None = None,
    ):
        self.rule = rule or KeywordRule()
        self.settings = settings or AnalogySettings()
        # 문제 정의 카드 설정(ADR 0065). None 이면 꺼짐 — 요청에 카드가 있어도 보지 않는다
        self.card_config = card_config
        self._remembered: _Memo = _Memo(256, 3600.0, time.monotonic)

    def remember(self, req: ProposalRequest, keywords: LiveKeywords) -> None:
        self._remembered.put(keyword_cache_key(req), keywords)

    def card_queries(self, req: ProposalRequest) -> CardQueries | None:
        """요청에 실린 카드의 질의 묶음 — 카드가 없거나 꺼져 있으면 None(종전 방식)."""
        return queries_for(req, self.card_config)

    def class_queries(self, req: ProposalRequest) -> list[str]:
        """분류 코드 검색 질의("ipc:" 표식) — 분류 검색을 하는 자료원(KIPRIS)만 받는다."""
        queries = self.card_queries(req)
        return [class_query(code) for code in queries.ipc] if queries is not None else []

    async def __call__(self, req: ProposalRequest) -> LiveKeywords:
        # 카드 질의는 요청에 실린 카드에서 그대로 만든다 — 입력 글 키의 기억(remember)을 거치지
        # 않는다(같은 입력·다른 카드가 서로 덮어쓰지 않게, 계약 4.1절 3)
        queries = self.card_queries(req)
        if queries is not None:
            return LiveKeywords(ko=list(queries.live_ko), en=list(queries.live_en), origin="rule")
        found = self._remembered.get(keyword_cache_key(req))
        if found is not None:
            return found
        axis = self.settings.axis
        terms = problem_terms(req, self.rule, axis)
        return LiveKeywords(
            ko=problem_phrases_ko(None, terms, axis, self.rule), en=[], origin="rule"
        )


@dataclass
class _Candidate:
    doc: Document
    similarity: float


class ProblemAnalogySearch:
    """`novel_contract.AnalogySearch` 구현.

    live: 유추 검색 전용 LiveSearch — `keywords=ProblemKeywords(...)`(같은 객체를
      `problem_keywords` 로도 넘긴다)·`keyword_cache=False`·config =
      `AnalogySettings.live.live_config(기존 live_search 설정)`. None 이면 저장 자료만.
    keyword_source: 평소 실시간 검색 키워드(영문 포함) — 보통 `LiveSearch.keywords_for`(24시간 캐시,
      Argon 을 다시 부르지 않는다). None·실패면 규칙 키워드(영문 없음 → OpenAlex 질의 없음).
    floor: 관련도 하한(overlap.yaml evidence_floor, 기본 0.79).
    """

    def __init__(
        self,
        repo: DocumentRepository,
        *,
        live: LiveSearchLike | None = None,
        problem_keywords: ProblemKeywords | None = None,
        keyword_source: KeywordSource | None = None,
        settings: AnalogySettings | None = None,
        rail: RailFieldRule | None = None,
        keywords: KeywordRule | None = None,
        floor: RelevanceFloor | None = None,
        include_internal: bool = True,
        memo_size: int = 64,
        memo_minutes: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        card_config: ProblemCardConfig | None = None,
        scorer: DocumentScorerPort | None = None,
        embedding: EmbeddingPort | None = None,
    ):
        self.repo = repo
        # 비슷한 자료 묶기(계약 4.6절)의 초록 의미 유사도 — None·실패면 제목 기준만으로 묶는다
        self.embedding = embedding
        # 문제 정의 카드(ADR 0065) — None 이면 꺼짐. scorer: 최종 정렬의 재순위(없으면 규칙 순)
        self.card_config = card_config
        self.scorer = scorer
        self.settings = settings or AnalogySettings()
        self.rail = rail or RailFieldRule()
        self.rule = keywords or KeywordRule()
        self.floor = floor or RelevanceFloor()
        self.keyword_source = keyword_source
        self.include_internal = include_internal
        self.live = live if self.settings.enabled else None
        if self.live is not None:
            inner = getattr(self.live, "keywords", None)
            if problem_keywords is None and isinstance(inner, ProblemKeywords):
                problem_keywords = inner
            if problem_keywords is None or inner is not problem_keywords:
                raise ValueError("유추 검색 LiveSearch 는 keywords=ProblemKeywords 로 만든다")
            if getattr(self.live, "keyword_cache", False):
                raise ValueError("유추 검색 LiveSearch 는 keyword_cache=False 로 만든다")
        self.problem_keywords = problem_keywords
        if problem_keywords is not None:
            # 실시간 검색 키워드와 저장 자료 질의가 같은 설정으로 같은 카드 질의를 보게 — 설정은
            # 이 객체 것 하나(꺼짐 포함)
            problem_keywords.card_config = card_config
        self._memo = _Memo(memo_size, memo_minutes * 60, clock)
        self._reports = _Memo(memo_size, memo_minutes * 60, clock)
        self.last_ranked: list[tuple[str, str, float | None, bool]] = []

    async def __call__(
        self, req: ProposalRequest, *, core_keywords: list[str] | None = None
    ) -> list[Analogy]:
        if not self.settings.enabled or self.settings.max_results <= 0:
            return []
        queries = queries_for(req, self.card_config)
        if queries is not None and req.problem_card is not None and self.card_config is not None:
            return await self._call_card(
                req, req.problem_card, queries, self.card_config, core_keywords
            )
        key = input_key(req, core_keywords or [])
        cached = self._memo.get(key)
        if cached is not None:
            return list(cached)
        axis = self.settings.axis
        base = await self._base_keywords(req)
        core = list(core_keywords) if core_keywords else list(base.ko)
        terms = problem_terms(req, self.rule, axis, core)
        if not terms:
            self._memo.put(key, [])
            return []
        phrases_ko = problem_phrases_ko(core, terms, axis, self.rule)
        phrases_en = problem_phrases_en(base.en, axis)
        summary = None
        if self.live is not None and self.live.enabled and self.problem_keywords is not None:
            self.problem_keywords.remember(
                req, LiveKeywords(ko=phrases_ko, en=phrases_en, origin=base.origin)
            )
            summary = await _prepare(self.live, ANALOGY_OWNER, req, "analogy")
        live_ids = set(summary.doc_ids) if summary is not None else set()
        query = problem_query(terms, phrases_en)
        found = await self._candidates(query)
        out = self._pick(found, terms, en_terms(phrases_en), live_ids)
        logger.info(
            "analogy.done terms=%d candidates=%d picked=%d live=%s",
            len(terms),
            len(found),
            len(out),
            summary is not None and summary.status in ("done", "partial"),
        )
        if summary is None or summary.status != "pending":
            self._memo.put(key, out)
        return list(out)

    # ── 문제 정의 카드 경로 (ADR 0065) ─────────────────────
    async def _call_card(
        self,
        req: ProposalRequest,
        card: ProblemCard,
        queries: CardQueries,
        config: ProblemCardConfig,
        core_keywords: list[str] | None,
    ) -> list[Analogy]:
        """카드 질의로 실시간 검색(세션 소유자 = 질의 지문) → 저장 자료를 질의마다 검색해 같은
        문서는 높은 유사도로 합침 → 최종 5건. 메모 키 = 입력 + 핵심어 + 검색·정렬 지문."""
        key = input_key(
            req,
            core_keywords or [],
            *memo_groups(pick_fingerprint(queries, card, config.rank, config.groups)),
        )
        cached = self._memo.get(key)
        if cached is not None:
            return list(cached)
        summary = None
        if self.live is not None and self.live.enabled and self.problem_keywords is not None:
            # 키워드는 ProblemKeywords 가 요청의 카드에서 그대로 만든다(remember 없음)
            summary = await _prepare(
                self.live, analogy_owner(ANALOGY_OWNER, queries), req, "analogy"
            )
        live_ids = set(summary.doc_ids) if summary is not None else set()
        # 제안문 문제어 질의(종전 규칙, AI 호출 없음) — 카드 기능 문장이 좁게 잡혀도 직접 관련
        # 자료가 후보·재순위에서 밀리지 않게 함께 쓴다(rank.with_request_query)
        request_query = ""
        if config.rank.with_request_query and config.uses("analogy_rank"):
            request_query = problem_query(problem_terms(req, self.rule, self.settings.axis), [])
        merged: dict[str, _Candidate] = {}
        request_found: list[_Candidate] = []  # 종전 문제어 질의의 후보 — 0건 안내에만 쓴다
        for query in [*queries.stored, request_query]:
            hits = await self._candidates(query)
            if query and query == request_query:
                request_found = hits
            for c in hits:
                old = merged.get(c.doc.doc_id)
                if old is None or c.similarity > old.similarity:
                    merged[c.doc.doc_id] = c
        found = list(merged.values())
        reranked = False
        report: AnalogyReport | None = None
        if config.uses("analogy_rank"):
            out, reranked, report = await self._pick_card(
                found, card, config, live_ids, request_query
            )
            # 검색 범위 — 실제로 확인한 자료원만(새로움 확인과 같은 규칙). 응답하지 않은 자료원이
            # 있으면 '없음'이 아니라 '일부만 확인'
            if not out and request_found:
                # 카드 방식만 0건인가(계약 4.4절) — 이미 받은 종전 질의 후보에 종전 고르기만 한 번
                # (저장소·자료원을 다시 부르지 않는다). 자료는 싣지 않고 건수만
                legacy_terms = problem_terms(req, self.rule, self.settings.axis)
                legacy = self._pick(request_found, legacy_terms, [], live_ids)
                report = report.model_copy(update={"legacy_count": len(legacy)})
            live_names = self._live_sources()
            coverage = build_coverage([], summary, live_sources=live_names)
            report = report.model_copy(
                update={
                    "searched": list(coverage.searched),
                    "unavailable": list(coverage.unavailable),
                    "sources_total": len(live_names),
                }
            )
        else:  # 질의만 카드 — 종전 정렬에 카드 문제어를 쓴다
            terms = card.terms
            out = self._pick(
                found,
                [*terms.objects_ko, *terms.actions_ko],
                [*terms.objects_en, *terms.actions_en],
                live_ids,
            )
        logger.info(
            "analogy.done card=1 queries=%d candidates=%d picked=%d live=%s reranked=%s "
            "few_analogies=%s",
            len(queries.stored),
            len(found),
            len(out),
            summary is not None and summary.status in ("done", "partial"),
            reranked,
            few_analogies(len(out)),
        )
        if report is not None:
            self._reports.put(key, report)
        if summary is None or summary.status != "pending":
            self._memo.put(key, out)
        return list(out)

    def _live_sources(self) -> list[str]:
        """유추 실시간 검색이 켜 둔 자료원(없으면 빈 목록)."""
        cfg = getattr(self.live, "config", None)
        if cfg is None or not getattr(self.live, "enabled", False):
            return []
        return list(cfg.enabled_sources())

    def details(
        self, req: ProposalRequest, *, core_keywords: list[str] | None = None
    ) -> AnalogyReport | None:
        """방금(같은 입력·같은 카드로) 한 유추 검색의 보고 — 카드 경로가 아니면 None."""
        queries = queries_for(req, self.card_config)
        card = req.problem_card
        if queries is None or card is None or self.card_config is None:
            return None
        key = input_key(
            req,
            core_keywords or [],
            *memo_groups(
                pick_fingerprint(queries, card, self.card_config.rank, self.card_config.groups)
            ),
        )
        return self._reports.get(key)

    def _eligible(
        self, found: Sequence[_Candidate], *, keep_rail: bool = False
    ) -> list[_Candidate]:
        """종전 규칙 — 하한·공용 계정 internal 제외·철도 분야 제외·같은 제목 제외(유사도 높은
        것을 남긴다). keep_rail: 카드의 대상이 철도 시설이면 철도 분야 자료를 거르지 않는다
        ('관련 선행 자료')."""
        out: list[_Candidate] = []
        seen_titles: set[str] = set()
        for c in sorted(found, key=lambda c: (-c.similarity, c.doc.doc_id)):
            doc = c.doc
            if c.similarity < self.floor.min_similarity:
                continue
            if not self.include_internal and doc.visibility == "internal":
                continue
            if not keep_rail and rail_reason(doc, self.rail) is not None:
                continue
            title_key = normalized_title(doc.title)
            if title_key and title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            out.append(c)
        return out

    async def _pick_card(
        self,
        found: Sequence[_Candidate],
        card: ProblemCard,
        config: ProblemCardConfig,
        live_ids: set[str],
        request_query: str = "",
    ) -> tuple[list[Analogy], bool, AnalogyReport]:
        """계약 4절 `analogy_rank` — (최종 목록, 재순위를 썼는가, 보고). 재순위 점수는 카드 기능
        문장 질의와 제안문 문제어 질의(request_query, 있으면) 중 높은 쪽. 5건을 억지로 채우지
        않는다 — 겹치는 제목·약한 자료를 뺀 만큼만."""
        rank = config.rank
        basis = rail_asset_basis(card, self.rail)  # 대상 자체가 철도 시설인가
        related = bool(basis)
        eligible = self._eligible(found, keep_rail=related)
        rows = rank_rows(
            [(c.doc, c.similarity) for c in eligible], card, rank, config.object_synonyms
        )
        if not rank.require_object:  # 대상어를 요구하지 않으면 종전처럼 한글 자료는 문제어 겹침
            rows = [
                r
                for r in rows
                if len(r.shared) >= self.settings.min_shared_terms
                or not has_hangul(f"{r.doc.title} {r.doc.abstract or ''}")
            ]
        scores: list[float] | None = None
        query = rerank_query(card)
        if self.scorer is not None and rows and query:
            try:
                pairs = [(r.doc, r.similarity) for r in rows]
                scores = [float(x) for x in await self.scorer.score_documents(query, pairs)]
                if request_query and len(scores) == len(rows):
                    extra = await self.scorer.score_documents(request_query, pairs)
                    if len(extra) == len(rows):
                        scores = [max(a, float(b)) for a, b in zip(scores, extra, strict=True)]
            except Exception as exc:  # 재순위 실패는 규칙 순으로 계속
                logger.warning("analogy.rerank_failed err=%s", type(exc).__name__)
                scores = None
            if scores is not None and len(scores) != len(rows):
                scores = None
        ordered = order_rows(rows, scores)
        distinct = drop_similar_titles(
            ordered, ratio=rank.dup_title_ratio, suffixes=rank.dup_title_suffixes
        )
        strong, weak = cut_weak(
            distinct,
            ratio=rank.weak_ratio,
            objects=object_terms(card, config.object_synonyms),
            keep_title_object=rank.weak_keep_title_object,
        )
        limit = min(self.settings.max_results, MAX_ANALOGIES)
        # 비슷한 자료는 지우지 않고 묶는다(계약 4.6절) — 묶음은 대표 한 자리만 차지하고, 자료원당
        # 우선은 대표들에 적용한다. 꺼져 있으면 자료마다 한 묶음(종전과 같다)
        grouped = await self._group(strong, config)
        members = {id(g.head): g.members for g in grouped}
        picked = take_by_source(
            [g.head for g in grouped],
            per_source=rank.per_source,
            limit=limit,
            window=rank.priority_window,
            min_ratio=rank.priority_min_ratio,
        )
        self.last_ranked = [  # 측정·진단용(제목·자료원·점수만) — 응답에 싣지 않는다
            (r.doc.title, r.doc.source, r.score, r in weak) for r in distinct[:20]
        ]
        report = AnalogyReport(
            kind=ANALOGY_RELATED if related else ANALOGY_OTHER_FIELD,
            rail_basis=basis,
            count=len(picked),
            candidates=len(eligible),
            # 약해서 뺀 탓에 비게 된 자리 수 — 어차피 5건 밖이던 자료는 세지 않는다
            dropped_weak=min(len(weak), max(0, limit - len(picked))),
            dropped_similar=len(ordered) - len(distinct),
            groups=sum(1 for r in picked if members.get(id(r))),
            group_analyze_max=config.groups.max_groups if config.group_analysis_on else 0,
        )
        out = [
            self._analogy(r, card, live_ids, related=related).model_copy(
                update={"similar": [self._member(m) for m in members.get(id(r), ())]}
            )
            for r in picked
        ]
        return out, scores is not None, report

    async def _group(
        self, strong: Sequence[RankRow], config: ProblemCardConfig
    ) -> list[Grouped[RankRow]]:
        """순위 순 목록 → 묶음 목록. 초록 유사도는 상위 window 건만 임베딩해 메모리에서 견준다
        (초록이 비면 제목). 임베딩이 없거나 실패하면 제목 기준만."""
        groups = config.groups
        if not config.groups_on or len(strong) < 2:
            return [Grouped(r) for r in strong]
        head = list(strong[: groups.window])
        sims: list[list[float]] | None = None
        if self.embedding is not None and groups.abstract_similarity > 0 and len(head) > 1:
            try:
                texts = [(r.doc.abstract or r.doc.title or "")[:GROUP_EMBED_CHARS] for r in head]
                sims = dot_matrix(await self.embedding.embed(texts))
            except Exception as exc:  # 임베딩 실패 — 제목 기준만으로 계속
                logger.warning("analogy.group_embed_failed err=%s", type(exc).__name__)
                sims = None
        return group_similar(
            strong,
            [r.doc.title for r in strong],
            title_ratio=groups.title_ratio,
            abstract_similarity=groups.abstract_similarity,
            window=groups.window,
            max_members=groups.max_members,
            suffixes=config.rank.dup_title_suffixes,
            similarities=sims,
        )

    def _member(self, row: RankRow) -> AnalogyMember:
        doc = row.doc
        return AnalogyMember(
            doc_id=doc.doc_id,
            title=doc.title,
            source=doc.source,
            source_label=SOURCE_LABELS.get(doc.source, doc.source),
            url=doc.url,
            year=doc.pub_date.year if doc.pub_date else None,
        )

    def _analogy(
        self, row: RankRow, card: ProblemCard, live_ids: set[str], *, related: bool = False
    ) -> Analogy:
        doc = row.doc
        shared = list(row.shared) or card_shared_terms(card, doc)
        return Analogy(
            doc_id=doc.doc_id,
            title=doc.title,
            source=doc.source,
            source_label=SOURCE_LABELS.get(doc.source, doc.source),
            domain_label=domain_label(doc),
            why_relevant=why_relevant(shared, row.similarity, related=related),
            url=doc.url,
            year=doc.pub_date.year if doc.pub_date else None,
            live=doc.doc_id in live_ids,
            similarity=round(row.similarity, 4),
        )

    async def _base_keywords(self, req: ProposalRequest) -> LiveKeywords:
        if self.keyword_source is not None:
            try:
                return await self.keyword_source(req)
            except Exception as exc:  # 키워드 실패는 규칙 키워드로
                logger.info("analogy.keywords_failed err=%s", type(exc).__name__)
        return rule_keywords(req, self.rule)

    async def _candidates(self, query: str) -> list[_Candidate]:
        if not query:
            return []
        sources = list(self.settings.search_sources) or None
        found: dict[str, _Candidate] = {}
        # 자료원별 최소 보장(2026-11-09): 자료원마다 상위 per_source 건을 먼저 — NTIS·ScienceON 국문
        # 요약이 e5 상위를 메워 KIPRIS 특허가 60 중 1건만 들던 것(ADR 0028 과 같은 현상). 그 뒤 전체
        # 순위로 search_k 까지. 같은 문서는 한 번. 순위 매김은 _pick 이 유사도로 다시 한다.
        per = self.settings.per_source
        if per > 0 and sources:
            for src in sources:
                try:
                    hits = await self.repo.find_similar(query, k=per, sources=[src])
                except Exception as exc:  # 한 자료원 실패는 건너뛴다
                    logger.warning(
                        "analogy.source_search_failed src=%s err=%s", src, type(exc).__name__
                    )
                    continue
                for d, s in hits:
                    found.setdefault(d.doc_id, _Candidate(d, float(s)))
        try:
            hits = await self.repo.find_similar(query, k=self.settings.search_k, sources=sources)
        except Exception as exc:  # 저장 자료 검색 실패 — 자료원별로 모은 것으로 계속
            logger.warning("analogy.search_failed err=%s", type(exc).__name__)
            return list(found.values())
        for d, s in hits:
            found.setdefault(d.doc_id, _Candidate(d, float(s)))
        return list(found.values())

    def _pick(
        self,
        found: Sequence[_Candidate],
        terms: Sequence[str],
        terms_en: Sequence[str],
        live_ids: set[str],
    ) -> list[Analogy]:
        ranked = sorted(found, key=lambda c: (-c.similarity, c.doc.doc_id))
        out: list[Analogy] = []
        seen_titles: set[str] = set()
        for c in ranked:
            doc = c.doc
            if c.similarity < self.floor.min_similarity:
                continue
            if not self.include_internal and doc.visibility == "internal":
                continue
            if rail_reason(doc, self.rail) is not None:
                continue
            shared = shared_terms(terms, terms_en, doc)
            korean = has_hangul(f"{doc.title} {doc.abstract or ''}")
            if korean and len(shared) < self.settings.min_shared_terms:
                continue  # 한글 자료는 문제어가 겹쳐야 (relevance 와 같은 뜻)
            title_key = normalized_title(doc.title)
            if title_key and title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            out.append(
                Analogy(
                    doc_id=doc.doc_id,
                    title=doc.title,
                    source=doc.source,
                    source_label=SOURCE_LABELS.get(doc.source, doc.source),
                    domain_label=domain_label(doc),
                    why_relevant=why_relevant(shared, c.similarity),
                    url=doc.url,
                    year=doc.pub_date.year if doc.pub_date else None,
                    live=doc.doc_id in live_ids,
                    similarity=round(c.similarity, 4),
                )
            )
            if len(out) >= min(self.settings.max_results, MAX_ANALOGIES):
                break
        return out
