"""제안서 초안 생성. 재개 가능하도록 세 단계로 나뉜다.

    retrieve(req)                    → RetrievalSnapshot  (검색 1회 + 유사과제 판정, 결과를 고정)
    compose_section(key, req, snap)  → 섹션 1개 (LLM 최대 1회, 섹션 단위 근거 검증까지)
    finalize(run_id, req, snap, …)   → Draft + lint 문제

섹션 종류 (rules.yaml 이 정한다):
- 문장형: JSON 배열. 근거 필수(evidence_required)·금지(evidence_forbidden)·선택.
- 선택형(choices): {"choices", "sentences"} 객체. 선택지는 앱 목록 안에서만, 확정은 사용자가 한다.
- 입력 전용(requires_input): 근거가 될 입력이 비면 LLM 을 부르지 않고 빈칸으로 둔다 (lint 경고).
- 고유명 대조(input_grounded): 정책·계획명·차수·연도가 허용 출처에 없으면 문장을 폐기한다.
- 수치 대조(number_checked): 수치가 입력·인용 청크에 없으면 lint 경고만 (finalize, 폐기 없음).
- overlap_review: 유사과제 판정에서 중복 기준을 넘는 것이 없으면 앱이 확정 문장을 쓴다 (LLM 미사용).
- 관련도 하한(relevance): 검색은 k×search_multiplier 로 넓게 받고, 유사도·키워드 조건을 넘지 못한
  것은 스냅샷에 넣지 않는다. 적재된 자료원 중 통과 청크가 min_per_source 에 못 미친 것은 그 자료원만
  다시 검색해 보탠 뒤(_top_up_sources) 출처마다 최소 min_per_source 건을 보장해(balance_sources)
  k 개로 줄인다 (`dropped_chunks` 에 이유만 남김). 남은 청크가 없으면 근거 필수 섹션은 LLM 을
  부르지 않고 빈칸(lint 경고 no_relevant_evidence). 유사과제 판정으로 보탠 청크(#overlap)는 하한을
  적용하지 않는다.

작성자(ADR 0032, [3]): writer_llm(Gemini 4 Argon)이 있으면 섹션을 그쪽이 먼저 쓰고(전송 범위 =
writer_include_internal, 공용 계정 run 은 internal 제외), 호출 실패(error·rate_limit·budget)나
교정 재요청 뒤에도 무효(invalid)인 섹션만 로컬 모델(llm)이 local_slot 을 잡고 쓴다. 없으면 예전
흐름(로컬 먼저 → ADR 0027 대체 작성). 섹션마다 작성 기록(ComposedSection.writer)을 남긴다
(본문 없음).

상태 저장·재개·동시성은 application/services/run_manager.py 가 맡는다.
`__call__` 은 세 단계를 한 번에 도는 조합이다 (테스트·일회성 실행용).

보안 A: LLM 출력은 JSON 만 받고, 근거 id 는 이번 run 의 검색 집합(스냅샷)과 대조한다.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from rra.application.ports import DocumentRepository, GenerationSlot, LLMPort, PromptLibraryPort
from rra.application.ports.auth import BudgetExhausted
from rra.application.ports.llm import RateLimited
from rra.application.ports.table_facts import TableFactRepository
from rra.domain.models import (
    Chunk,
    Document,
    Draft,
    OverlapAlert,
    ProposalRequest,
    RetrievalSnapshot,
    Section,
    Sentence,
    StrategyCatalog,
)
from rra.domain.models.outline import Outline
from rra.domain.models.selection import (
    STRATEGY_SOURCE,
    TASK_TYPES,
    TASK_TYPES_SOURCE,
    UTILIZATION,
    UTILIZATION_SOURCE,
)
from rra.domain.rules import style
from rra.domain.rules.exemplars import pick_exemplars
from rra.domain.rules.grounding import ungrounded
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.lint import (
    ChoiceSpec,
    LintProblem,
    LintRules,
    evidence_skipped_sections,
    has_errors,
    lint,
    skipped_sections,
)
from rra.domain.rules.llm_output import (
    EMPTY_HINT,
    ParseResult,
    correction_hint,
    dropped_hint,
    parse_choice_section,
    parse_sentences,
)
from rra.domain.rules.overlap import (
    OwnUnit,
    judge,
    no_overlap_statement,
    tier_of,
    uncollected_sources,
)
from rra.domain.rules.relevance import (
    DropReason,
    RelevanceFloor,
    balance_sources,
    filter_chunks,
)
from rra.domain.rules.retrieval_mix import RetrievalMix
from rra.domain.rules.retrieval_scope import overlap_candidates
from rra.domain.rules.rewrite import merge_candidate
from rra.domain.rules.schedule import (
    METRIC_SECTIONS,
    SCHEDULE_SECTION,
    metric_instruction,
    research_period_months,
    schedule_instruction,
    schedule_problems,
)
from rra.domain.rules.section_search import clip_chunks, section_queries
from rra.domain.rules.similar_choice import missing_similar_ids, rows_for_writing
from rra.domain.rules.trust import enforce_section_evidence, escape_untrusted, wrap_untrusted
from rra.domain.rules.writer import (
    LOCAL_CHECK_SYSTEM,
    LOCAL_CHECK_TIMEOUT_SEC,
    local_check_prompt,
    mismatch_hashes,
    parse_local_check,
    writer_record,
)

logger = logging.getLogger("rra.generate")

OVERLAP_SECTION = "overlap_review"
MAX_CHOSEN_EXTRA = 5  # ② 에서 [유사함] 으로 골랐지만 판정에 없는 문서 — 더 읽는 상한
_OVERLAP_TEXT_CHARS = 1500
# 제안자가 정한 차별화 방향(기능 2)을 지시문으로 넣는 섹션 — 목적·방법·특이사항
DIFFERENTIATION_SECTIONS = frozenset({"objective", "method", OVERLAP_SECTION})
CHOICE_EXAMPLE = (
    '{"choices": ["예시-id"], "sentences": [{"text": "예시 문장임.", "evidence": ["doc:예시#0"]}]}'
)
# Q7 두 후보를 쓰는 핵심 섹션 (기술적 중요도·연구방법) — 1차 검토가 고른다
CORE_SECTIONS = frozenset({"tech_importance", "method"})
EXEMPLAR_DROP = "exemplar_cited"  # Q4 본보기 문장을 그대로 베낀 경우
SECTION_POOL_MULTIPLIER = 4  # Q3 섹션별 검색 후보 폭 (관련도 하한이 없을 때)
# P2-8 스냅샷에 고정하는 표 사실 상한 (state.json 크기·화면 폴링). 큰 시트(역별·시간대별 수만 칸)는
# 일부만 들어간다 — 연도·단위가 있는 사실을 앞세운다. 전부 보려면 lint 시점 지연 조회(비동기 lint
# 경로)가 필요 — 후속.
MAX_FACTS_PER_DOC = 300
MAX_SNAPSHOT_FACTS = 2000

ComposeMode = Literal["llm", "skipped", "app"]


class DraftInvalid(Exception):
    def __init__(self, problems, dropped):
        super().__init__(f"{len(problems)} lint problems, {len(dropped)} sentences dropped")
        self.problems, self.dropped = problems, dropped


@dataclass(frozen=True)
class ComposedSection:
    section: Section
    dropped: list[str]
    # 시스템 프롬프트 + 섹션 지시문 해시 (입력·자료 미포함). LLM 미사용이면 None
    prompt_hash: str | None
    parse: ParseResult | None  # 파싱 사유·원본 길이. LLM 미사용이면 None
    mode: ComposeMode = "llm"  # skipped: 입력·목록이 비어 빈칸 / app: 앱 확정 문장
    # dropped 중 고유명 대조(정책명 등)로 폐기된 것
    ungrounded: list[str] = field(default_factory=list)
    retries: int = 0  # 형식 교정 재요청 횟수 (0 또는 1)
    # 첫 응답의 파싱 결과 (벤치 (a) 지표용). 재요청이 없었으면 parse 와 같다
    first_parse: ParseResult | None = None
    # 대체 작성(ADR 0027): 로컬 교정 재요청까지 실패한 섹션을 외부 LLM 이 썼다 — 전송 기록(본문
    # 없음)
    # {provider, model, reason, public_doc_ids, internal_doc_ids, calls}. 로컬이 썼으면 None
    fallback: dict[str, Any] | None = None
    # 대체 작성을 시도하지 못한/실패한 이유 (budget | 예외 클래스명 | parse 상태). 시도 없으면 None
    fallback_error: str | None = None
    # 작성 기록(ADR 0032, domain/rules/writer.writer_record): 누가 썼는지·로컬 대체 여부·사유·전송
    # doc_id·원격 호출 수. LLM 을 쓰지 않은 섹션(skipped·app)은 None
    writer: dict[str, Any] | None = None


@dataclass(frozen=True)
class _Job:
    """섹션 한 개 작성에 필요한 고정 값 (작성자마다 같은 지시·입력·스냅샷)."""

    key: str
    instruction: str
    system: str
    req: ProposalRequest
    snapshot: RetrievalSnapshot
    spec: ChoiceSpec | None
    options: dict[str, dict[str, str]]
    required: bool
    outline: Outline | None = None
    candidate: Section | None = None
    notes: Mapping[str, str] | None = None
    keep: Sequence[str] = ()

    @property
    def opts(self) -> dict[str, str] | None:
        return self.options.get(self.key) if self.spec else None


@dataclass
class _Attempt:
    first: ParseResult
    parsed: ParseResult
    section: Section
    dropped: list[str]
    lost: list[str]
    retries: int


class _Counted:
    """원격 작성 호출 수를 센다 — 예산 초과(BudgetExhausted)는 보내지 않았으므로 세지 않는다."""

    def __init__(self, llm: LLMPort):
        self.llm = llm
        self.calls = 0

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        try:
            out = await self.llm.complete(
                prompt, system=system, max_tokens=max_tokens, json_mode=json_mode
            )
        except BudgetExhausted:
            raise
        except Exception:
            self.calls += 1
            raise
        self.calls += 1
        return out


def remote_failure_reason(exc: BaseException) -> str:
    """원격 작성 호출 예외 → 로컬 대체 사유 (domain/rules/writer.REASONS)."""
    if isinstance(exc, BudgetExhausted):
        return "budget"
    if isinstance(exc, RateLimited):
        return "rate_limit"
    return "error"


@dataclass
class GenerateProposal:
    llm: LLMPort
    repo: DocumentRepository
    prompts: PromptLibraryPort
    rules: LintRules
    section_keys: list[str]
    k: int = 20
    strategy: StrategyCatalog = field(default_factory=StrategyCatalog)
    # 유사과제 판정 (5. 특이사항). None 이면 판정하지 않는다 → overlap_review 도 LLM 이 쓴다
    own: OwnUnit | None = None
    check_overlap: bool = False
    overlap_k: int = 10
    keywords: KeywordRule | None = None  # 차단에 키워드 조건을 더한다 (None 이면 유사도만)
    # 생성 근거의 관련도 하한 (이슈 #2). None 이면 검색 결과를 그대로 근거로 쓴다
    relevance: RelevanceFloor | None = None
    # ── [Q] 품질 단계 — config/pipeline.yaml 로 켜고 조립(composition)이 넣는다 ──
    reranker: Any | None = None  # Q8 RerankerPort: 하이브리드 후보를 cross-encoder 로 다시 순위
    section_search: bool = False  # Q3 섹션별 맞춤 검색 (retrieve_sections)
    section_k: int = 8  # 섹션 질의당 고르는 청크 수
    exemplars: bool = False  # Q4 채택 과제 본보기 (구성·문체 참고, 인용 금지)
    exemplar_limit: int = 2
    exemplar_exclude: frozenset[str] = frozenset()  # 본보기에서 뺄 doc_id (골든셋 정답 과제 등)
    rule_check: bool = True  # Q6 규칙 검사·자동 정리 (finalize, Argon 전)
    max_sentence_chars: int = style.DEFAULT_MAX_SENTENCE_CHARS
    # 근거 구성 규칙(config/retrieval_mix.yaml): 섹션별 허용 doc_type·논문 최소 보장·유사과제 제외
    mix: RetrievalMix | None = None
    # U6 제약에 연구기간이 있으면 연구방법에 추진일정(개월), 기대효과에 성과지표·측정 방법을
    # 요구하고
    # 일정 합이 기간을 넘으면 경고. config/usability.yaml schedule_metrics
    schedule_metrics: bool = True
    # 섹션 프롬프트 [자료] 상한 (pipeline.yaml chunk_max_chars·base_chunk_limit, 0 = 없음)
    chunk_max_chars: int = 0
    base_chunk_limit: int = 0
    # 대체 작성(ADR 0027): 로컬 교정 재요청까지 실패한 섹션만 외부 LLM(Gemini)이 쓴다. None 이면
    # 없음.
    # 전송 범위는 검토와 같다 — fallback_include_internal=False 면 internal 청크를 빼고 준다
    fallback_llm: LLMPort | None = None
    fallback_provider: str = ""
    fallback_model: str = ""
    fallback_include_internal: bool = True
    # ── [3] Argon 먼저 작성 (ADR 0032, llm.yaml compose.writer) ──
    # writer_llm 이 있으면 섹션을 그 LLM 이 먼저 쓰고, 실패 섹션만 로컬(llm)이 쓴다.
    # None 이면 예전 흐름
    writer_llm: LLMPort | None = None
    writer_provider: str = ""
    writer_model: str = ""
    # 원격 작성 전송 범위 — False 면 internal 청크·본보기를 빼고 보낸다 (공용 계정 run, 검토 정책)
    writer_include_internal: bool = True
    local_provider: str = "mlx"  # 작성 기록에 남길 로컬 provider·model 이름
    local_model: str = ""
    # 로컬 모델 단계(로컬 대체 작성·local_check)가 잡는 프로세스 간 슬롯 (원격 작성일 때만 잡는다).
    # 로컬 작성일 때는 RunManager 가 run 전체를 슬롯 안에서 돌린다
    local_slot: GenerationSlot | None = None
    compose_concurrency: int = 1  # 한 run 안에서 동시에 쓰는 섹션 수 (원격 작성일 때만 쓴다)
    local_check: bool = False  # 근거 있는 문장을 로컬 모델이 지지|부분|불일치 로 판정 (경고만)
    local_check_timeout: float = LOCAL_CHECK_TIMEOUT_SEC  # 섹션당 상한(초). 넘으면 그 섹션은 건너뜀

    @property
    def template(self) -> str | None:
        return self.rules.template

    @property
    def writes_remotely(self) -> bool:
        """섹션 작성을 원격 LLM(Argon)이 먼저 하는가 — RunManager 의 동시성 규칙이 이것을 본다."""
        return self.writer_llm is not None

    @property
    def writer(self) -> str:
        return "gemini" if self.writer_llm is not None else "local"

    def local_gate(self) -> contextlib.AbstractAsyncContextManager[None]:
        """로컬 모델을 부르는 구간 — 원격 작성이면 local_slot 을 잡는다(한 번에 하나)."""
        if self.writer_llm is not None and self.local_slot is not None:
            return self.local_slot.acquire()
        return contextlib.nullcontext()

    def choice_options(self) -> dict[str, dict[str, str]]:
        """선택형 섹션 → {선택지 id: 표시 이름}. 전략 목록이 비면 빈 dict."""
        sources = {
            TASK_TYPES_SOURCE: TASK_TYPES,
            UTILIZATION_SOURCE: UTILIZATION,
            STRATEGY_SOURCE: self.strategy.options(),
        }
        return {key: dict(sources[spec.options]) for key, spec in self.rules.choices.items()}

    # ── retrieve ─────────────────────────────────────────
    async def retrieve(self, req: ProposalRequest) -> RetrievalSnapshot:
        query = req.search_text()
        wide = self.k * (self.relevance.search_multiplier if self.relevance else 1)
        chunks = list(await self.repo.hybrid_search([query], k=wide))
        dropped: dict[str, str] = {}
        if self.relevance is not None:
            keywords = self.keywords or KeywordRule()
            chunks, removed = filter_chunks(chunks, query, self.relevance, keywords)
            dropped = {c.chunk_id: reason for c, reason in removed}
            extra, more = await self._top_up_sources(query, chunks)
            dropped.update({c.chunk_id: reason for c, reason in more})
            pool = await self._rerank(query, chunks + extra)  # Q8: 자료원 보장 전에 다시 순위
            chunks = balance_sources(pool, self.k, self.relevance.min_per_source)
        else:
            chunks = (await self._rerank(query, chunks))[: self.k]
        if not self.check_overlap and not self.exemplars:
            snapshot = RetrievalSnapshot.of(query, chunks)
            snapshot.dropped_chunks = dropped
            await self._fill_doc_types(snapshot)
            await self._fill_facts(snapshot)
            return snapshot
        hits = await self.repo.find_similar(query, k=max(self.overlap_k, self.exemplar_limit * 5))
        hits = overlap_candidates(hits)  # 정책·보도 자료원은 유사과제가 아니다 (retrieval_scope)
        if self.mix is not None:  # doc_type 기준 제외(retrieval_mix.overlap_exclude)
            hits = self.mix.overlap_candidates(hits, lambda d: d.doc_type)
        if not self.check_overlap:
            snapshot = RetrievalSnapshot.of(query, chunks)
        else:
            alerts = judge(
                hits[: self.overlap_k], own=self.own, query=query, keywords=self.keywords
            )
            # ② 제안자 선택(레인 A): [관련 없음] 행은 빼고 [유사함] 행은 중복 검토 대상으로 — 선택한
            # 문서가 이번 판정에 없으면 문서를 읽어 더한다 (선택이 없으면 종전 그대로)
            alerts, hits = await self._apply_similar_choices(req, alerts, hits)
            extra = self._overlap_chunks(hits, alerts, chunks)
            snapshot = RetrievalSnapshot.of(query, chunks + extra, alerts)
            snapshot.uncollected = uncollected_sources(await self.repo.count_by_source())
        snapshot.dropped_chunks = dropped
        if self.exemplars:  # Q4: 유사도 순 후보에서 완료·수행 과제의 공개 요약을 본보기로
            snapshot.exemplars = pick_exemplars(
                hits, limit=self.exemplar_limit, exclude=self.exemplar_exclude
            )
        await self._fill_doc_types(snapshot)
        await self._fill_facts(snapshot)
        return snapshot

    async def _apply_similar_choices(
        self,
        req: ProposalRequest,
        alerts: list[OverlapAlert],
        hits: list[tuple[Document, float]],
    ) -> tuple[list[OverlapAlert], list[tuple[Document, float]]]:
        choices = req.choice_map()
        if not choices:
            return alerts, hits
        rows = rows_for_writing(alerts, choices)
        hits = list(hits)
        for doc_id in missing_similar_ids(rows, choices)[:MAX_CHOSEN_EXTRA]:
            doc = await self.repo.get_document(doc_id)
            if doc is None:  # 공용 계정 run 은 internal 문서를 읽지 못한다 — 그대로 둔다
                continue
            rows.append(
                OverlapAlert(
                    doc_id=doc.doc_id,
                    title=doc.title,
                    tier=tier_of(doc, self.own),
                    similarity=0.0,
                    blocking=True,
                    basis=doc.text_basis,
                    choice="similar",
                )
            )
            hits.append((doc, 0.0))
        return rows, hits

    async def _fill_facts(self, snapshot: RetrievalSnapshot) -> None:
        """P2-8 표 사실 — 검색 집합 문서의 사실을 스냅샷에 고정한다(수치 lint 근거). 저장소가 사실을
        모르면(fake·옛 어댑터) 비워 둔다 = 종전 동작."""
        if not isinstance(self.repo, TableFactRepository):
            return
        doc_ids = sorted({c.doc_id for c in snapshot.chunks} - set(snapshot.facts))
        if not doc_ids:
            return
        found = await self.repo.facts_for(doc_ids)
        budget = MAX_SNAPSHOT_FACTS - sum(len(v) for v in snapshot.facts.values())
        for doc_id in doc_ids:
            facts = found.get(doc_id) or []
            if not facts or budget <= 0:
                continue
            ranked = sorted(facts, key=lambda f: (f.year is None, f.unit is None))
            kept = ranked[: min(MAX_FACTS_PER_DOC, budget)]
            snapshot.facts[doc_id] = kept
            budget -= len(kept)

    async def _fill_doc_types(self, snapshot: RetrievalSnapshot) -> None:
        """근거 구성 규칙용 doc_id → doc_type (규칙이 있을 때만, 문서마다 1회 조회)."""
        if self.mix is None:
            return
        for doc_id in {c.doc_id for c in snapshot.chunks}:
            if doc_id in snapshot.doc_types:
                continue
            doc = await self.repo.get_document(doc_id)
            if doc is not None:
                snapshot.doc_types[doc_id] = doc.doc_type

    async def _rerank(self, query: str, chunks: list[Chunk]) -> list[Chunk]:
        if self.reranker is None or not chunks:
            return chunks
        return list(await self.reranker.rerank(query, chunks))

    async def retrieve_sections(
        self, req: ProposalRequest, snapshot: RetrievalSnapshot, outline: Outline | None = None
    ) -> RetrievalSnapshot:
        """Q3 섹션별 맞춤 검색 — 섹션 질의(입력 칸 + 설계도 메시지)로 다시 검색해 섹션이 쓸 청크를
        고른다. 새 청크는 스냅샷에 더해 근거 대조 집합에도 들어간다. 같은 관련도 하한·reranker."""
        if not self.section_search:
            return snapshot
        queries = section_queries(req, self.section_keys, outline)
        have = {c.chunk_id for c in snapshot.chunks}
        # 후보는 넓게(k×배수) 받아야 허용 doc_type·자료원 보장·논문 최소 보장을 채울 수 있다
        multiplier = self.relevance.search_multiplier if self.relevance else SECTION_POOL_MULTIPLIER
        for key, query in queries.items():
            found = list(await self.repo.hybrid_search([query], k=self.section_k * multiplier))
            if self.relevance is not None:
                found, _ = filter_chunks(
                    found, query, self.relevance, self.keywords or KeywordRule()
                )
            ranked = await self._rerank(query, found)
            for c in ranked:  # doc_type 을 먼저 알아야 섹션 허용 규칙을 적용할 수 있다
                if c.chunk_id not in have:
                    have.add(c.chunk_id)
                    snapshot.chunks.append(c)
                    snapshot.section_added.append(c.chunk_id)
            await self._fill_doc_types(snapshot)
            if self.mix is not None:
                ranked = self.mix.filter(key, ranked, snapshot.doc_types)
            per_source = (
                self.mix.section_min_per_source
                if self.mix is not None
                else (max(1, self.relevance.min_per_source // 3) if self.relevance else 0)
            )
            if per_source > 0:
                # 섹션 근거도 자료원 섞임을 지킨다 — 한국어 섹션 질의는 논문을 뒤로 밀기 때문
                picked = balance_sources(ranked, self.section_k, per_source)
            else:
                picked = ranked[: self.section_k]
            if self.mix is not None:  # 기술적 중요도·연구방법은 논문·보고서·특허 최소 보장
                picked = self.mix.top_up_scholarly(key, picked, ranked, snapshot.doc_types)
            if picked:
                snapshot.section_chunks[key] = [c.chunk_id for c in picked]
        await self._fill_facts(snapshot)  # 섹션 검색이 더한 문서의 표 사실
        return snapshot

    async def _top_up_sources(
        self, query: str, kept: list[Chunk]
    ) -> tuple[list[Chunk], list[tuple[Chunk, DropReason]]]:
        """넓은 검색에서도 min_per_source 에 못 미친 자료원은 그 자료원만으로 다시 검색해 보탠다.

        한국어 질의는 융합 순위 상위를 사내 기록이 메워 영어 논문이 상위 160 안에도 거의 없다
        (2026-10-26). 자료원 필터 검색 결과도 같은 관련도 하한을 거치며, 넓은 검색 목록 뒤에 붙어
        balance_sources 가 보장분만 고른다. 적재된 자료원(count_by_source) 만 본다.
        """
        floor = self.relevance
        need = floor.min_per_source if floor is not None else 0
        if floor is None or need <= 0:
            return [], []
        have: dict[str, int] = {}
        for c in kept:
            src = c.doc_id.split(":", 1)[0]
            have[src] = have.get(src, 0) + 1
        seen = {c.chunk_id for c in kept}
        extra: list[Chunk] = []
        removed: list[tuple[Chunk, DropReason]] = []
        for src in sorted(await self.repo.count_by_source()):
            if have.get(src, 0) >= need:
                continue
            found = await self.repo.hybrid_search(
                [query], k=need * floor.search_multiplier, sources=[src]
            )
            ok, bad = filter_chunks(
                [c for c in found if c.chunk_id not in seen],
                query,
                floor,
                self.keywords or KeywordRule(),
            )
            removed.extend(bad)
            for c in ok[: need - have.get(src, 0)]:
                seen.add(c.chunk_id)
                extra.append(c)
        return extra, removed

    def evidence_skipped(self, snapshot: RetrievalSnapshot) -> dict[str, str]:
        """근거 청크가 없어 빈칸으로 두는 근거 필수 섹션. 유사과제 판정을 했으면 특이사항은 예외."""
        exempt = {OVERLAP_SECTION} if snapshot.overlap_checked else set()
        return evidence_skipped_sections(self.rules, snapshot, exempt)

    @staticmethod
    def _overlap_chunks(
        hits: list[tuple[Document, float]], alerts: list[OverlapAlert], chunks: list[Chunk]
    ) -> list[Chunk]:
        """중복 기준을 넘은 문서가 검색 청크에 없으면 제목·초록으로 청크 하나를 만든다 (비신뢰)."""
        have = {c.doc_id for c in chunks}
        blocking = {a.doc_id for a in alerts if a.blocking}
        out: list[Chunk] = []
        for doc, _ in hits:
            if doc.doc_id not in blocking or doc.doc_id in have:
                continue
            body = (doc.abstract or doc.body or "")[:_OVERLAP_TEXT_CHARS]
            out.append(
                Chunk(
                    chunk_id=f"{doc.doc_id}#overlap",
                    doc_id=doc.doc_id,
                    ordinal=0,
                    text=f"{doc.title}\n{body}".strip(),
                    basis=doc.text_basis,
                )
            )
            have.add(doc.doc_id)
        return out

    # ── compose ──────────────────────────────────────────
    async def compose_section(
        self,
        key: str,
        req: ProposalRequest,
        snapshot: RetrievalSnapshot,
        *,
        outline: Outline | None = None,
        candidate: Section | None = None,
    ) -> ComposedSection:
        """섹션 1개. outline(Q2)은 그 섹션 설계와 전체 요약을, candidate(Q7)는 이미 쓴 후보 A 를
        주고 다른 구성의 후보 B 를 쓰게 한다. 본보기(Q4)는 스냅샷에 있으면 넣는다."""
        options = self.choice_options()
        if key in skipped_sections(req, self.rules, options) or key in self.evidence_skipped(
            snapshot
        ):
            return ComposedSection(Section(key=key, sentences=[]), [], None, None, "skipped")
        if key == OVERLAP_SECTION and snapshot.overlap_checked:
            if not any(a.blocking for a in snapshot.overlap):
                texts = no_overlap_statement(snapshot.scope, snapshot.uncollected)
                sentences = [Sentence(text=t, origin="app") for t in texts]
                section = Section(key=key, sentences=sentences)
                return ComposedSection(section, [], None, None, "app")

        return await self._compose_llm(
            key, req, snapshot, options, outline=outline, candidate=candidate
        )

    async def rewrite_section(
        self,
        key: str,
        req: ProposalRequest,
        snapshot: RetrievalSnapshot,
        current: Section,
        notes: Mapping[str, str] | None = None,
    ) -> ComposedSection:
        """U3 섹션 하나 다시 쓰기 — 같은 지시·같은 스냅샷 근거로 LLM 1회. 제안자가 고친 문장
        (proposer_edit·proposer_input·app)은 보존해 후보에 원래 자리로 끼워 넣고, 선택값은 그대로.
        notes: 보완 질문에 대한 제안자 답({요소: 답}) — 지시문 뒤에 [제안자 보완 메모] 로."""
        options = self.choice_options()
        if key in skipped_sections(req, self.rules, options) or key in self.evidence_skipped(
            snapshot
        ):
            return ComposedSection(Section(key=key, sentences=[]), [], None, None, "skipped")
        if key == OVERLAP_SECTION and snapshot.overlap_checked:
            raise ValueError(
                "특이사항(유사과제 검토 결과)은 앱이 쓰는 섹션이라 다시 쓰지 않습니다."
            )
        keep = [
            s.text
            for s in current.sentences
            if s.origin in ("proposer_edit", "proposer_input", "proposer", "app")
        ]
        composed = await self._compose_llm(key, req, snapshot, options, notes=notes, keep=keep)
        merged = merge_candidate(current, composed.section.sentences)
        return ComposedSection(
            section=merged,
            dropped=composed.dropped,
            prompt_hash=composed.prompt_hash,
            parse=composed.parse,
            ungrounded=composed.ungrounded,
            retries=composed.retries,
            first_parse=composed.first_parse,
            writer=composed.writer,
        )

    async def _compose_llm(
        self,
        key: str,
        req: ProposalRequest,
        snapshot: RetrievalSnapshot,
        options: dict[str, dict[str, str]],
        *,
        outline: Outline | None = None,
        candidate: Section | None = None,
        notes: Mapping[str, str] | None = None,
        keep: Sequence[str] = (),
    ) -> ComposedSection:
        spec = self.rules.choices.get(key)
        job = _Job(
            key=key,
            instruction=self.prompts.section(key),
            system=self.prompts.system(),
            req=req,
            snapshot=snapshot,
            spec=spec,
            options=options,
            required=key in self.rules.required_sections,
            outline=outline,
            candidate=candidate,
            notes=notes,
            keep=keep,
        )
        if self.writer_llm is not None:
            return await self._compose_remote_first(job)
        system, instruction, required = job.system, job.instruction, job.required
        att = await self._attempt(self.llm, job)
        first, parsed, section = att.first, att.parsed, att.section
        dropped, lost, retries = att.dropped, att.lost, att.retries

        fallback: dict[str, Any] | None = None
        fallback_error: str | None = None
        if self._bad(parsed, section, required) and self.fallback_llm is not None:
            # 대체 작성(ADR 0027) — 로컬 2회 실패 뒤에만. 전송 범위는 검토와 같다.
            reason = self._failure_reason(parsed, section)
            shown = self._fallback_chunks(key, snapshot)
            compact = self._prompt(
                key,
                instruction,
                req,
                snapshot,
                options.get(key) if spec else None,
                compact=True,
                chunks=shown,
            )
            try:
                raw3 = await self.fallback_llm.complete(compact, system=system, json_mode=True)
            except BudgetExhausted:
                fallback_error = "budget"
            except Exception as exc:  # 네트워크·인증 등 — 실패 섹션으로 남긴다 (메시지 로그 없음)
                fallback_error = type(exc).__name__
            else:
                third = self._parse(key, raw3, spec, options)
                # 보안 A: 대체 작성 문장의 근거 id 는 "보여 준 청크" 집합과 대조한다
                shown_ids = (
                    {c.chunk_id for c in shown}
                    | {c.doc_id for c in shown}
                    | {a.doc_id for a in snapshot.overlap}
                )
                section3, dropped3, lost3 = self._validate(key, third, shown_ids, req, snapshot)
                if not self._bad(third, section3, required):
                    parsed, section, dropped, lost = third, section3, dropped3, lost3
                    internal = internal_doc_ids(snapshot.chunks)
                    fallback = {
                        "provider": self.fallback_provider,
                        "model": self.fallback_model,
                        "reason": reason,
                        "public_doc_ids": sorted(
                            {c.doc_id for c in shown if c.doc_id not in internal}
                        ),
                        "internal_doc_ids": sorted(
                            {c.doc_id for c in shown if c.doc_id in internal}
                        ),
                        "calls": 1,
                    }
                else:
                    fallback_error = self._failure_reason(third, section3)
            logger.warning(
                "compose.fallback section=%s reason=%s result=%s",
                key,
                reason,
                "ok" if fallback else fallback_error,
            )

        digest = hashlib.sha256(f"{system}\x1f{instruction}".encode()).hexdigest()[:16]
        if fallback is not None:
            writer = writer_record(
                provider=fallback["provider"],
                model=fallback["model"],
                public_doc_ids=fallback["public_doc_ids"],
                internal_doc_ids=fallback["internal_doc_ids"],
                calls=fallback["calls"],
            )
        else:
            writer = writer_record(provider=self.local_provider, model=self.local_model)
        return ComposedSection(
            section=section,
            dropped=dropped,
            prompt_hash=digest,
            parse=parsed,
            ungrounded=lost,
            retries=retries,
            first_parse=first,
            fallback=fallback,
            fallback_error=fallback_error,
            writer=writer,
        )

    async def _attempt(
        self,
        llm: LLMPort,
        job: _Job,
        *,
        chunks: list[Chunk] | None = None,
        allowed: set[str] | None = None,
        exemplars: bool = True,
    ) -> _Attempt:
        """작성 1회 + 형식 교정 재요청 1회. chunks 를 주면 그 [자료] 만 보여 주고(전송 범위),
        allowed 를 주면 근거 id 를 그 집합과 대조한다(보안 A — 기본은 스냅샷 전체)."""
        key, snapshot, spec = job.key, job.snapshot, job.spec
        allowed_ids = snapshot.retrieved_ids if allowed is None else allowed
        prompt = self._prompt(
            key,
            job.instruction,
            job.req,
            snapshot,
            job.opts,
            outline=job.outline,
            candidate=job.candidate,
            notes=job.notes,
            keep=job.keep,
            chunks=chunks,
            exemplars=exemplars,
        )
        raw = await llm.complete(prompt, system=job.system, json_mode=True)
        first = parsed = self._parse(key, raw, spec, job.options)
        section, dropped, lost = self._validate(key, parsed, allowed_ids, job.req, snapshot)
        retries = 0
        if self._bad(parsed, section, job.required):
            # 스키마·JSON 오류, 필수 섹션의 빈 문장 목록, 검증(근거·고유명)에서 전부 폐기 —
            # 1회 재요청. 오류 요약을 붙여 같은 섹션을 다시 묻는다
            retries = 1
            hint = self._hint(parsed, dropped, choice_section=spec is not None)
            # 재요청은 기본 프롬프트로(설계도·본보기·후보·메모 없이) — 긴 지시가 붙을수록 7B 가 JSON
            # 대신 글을 쓴다(2026-10-27 측정: 제목·활용계획에서 반복)
            compact = self._prompt(
                key, job.instruction, job.req, snapshot, job.opts, compact=True, chunks=chunks
            )
            raw2 = await llm.complete(
                f"{compact}\n\n[형식 교정 — 직전 응답은 형식 오류였음]\n{hint}",
                system=job.system,
                json_mode=True,
            )
            second = self._parse(key, raw2, spec, job.options)
            section2, dropped2, lost2 = self._validate(key, second, allowed_ids, job.req, snapshot)
            if not self._bad(second, section2, job.required) or (
                second.status == "choices_only" and not parsed.choices
            ):
                parsed, section, dropped, lost = second, section2, dropped2, lost2
            elif second.ok and parsed.ok and second.choices and not parsed.choices:
                parsed, section, dropped, lost = second, section2, dropped2, lost2
            # 두 번째도 실패하면 첫 결과로 기존처럼 처리한다
        return _Attempt(first, parsed, section, dropped, lost, retries)

    async def _compose_remote_first(self, job: _Job) -> ComposedSection:
        """ADR 0032 — Argon 이 먼저 쓰고(전송 범위 적용), 실패하면 로컬 모델이 local_slot 을
        잡고 쓴다. 로컬 대체 사유: 호출 예외 → error | rate_limit | budget, 교정 재요청 뒤에도
        무효 → invalid."""
        if self.writer_llm is None:
            raise RuntimeError("writer_llm missing")
        key, snapshot = job.key, job.snapshot
        shown = self._writer_chunks(key, snapshot)
        # 보안 A: 원격 작성 문장의 근거 id 는 "보여 준 청크" 집합과 대조한다
        shown_ids = (
            {c.chunk_id for c in shown}
            | {c.doc_id for c in shown}
            | {a.doc_id for a in snapshot.overlap}
        )
        remote = _Counted(self.writer_llm)
        reason: str | None = None
        att: _Attempt | None = None
        try:
            att = await self._attempt(
                remote,
                job,
                chunks=shown,
                allowed=shown_ids,
                exemplars=self.writer_include_internal,
            )
        except Exception as exc:  # 네트워크·429·예산 — 그 섹션만 로컬로 (메시지 로그 없음)
            reason = remote_failure_reason(exc)
            logger.warning(
                "compose.writer_failed section=%s reason=%s error=%s",
                key,
                reason,
                type(exc).__name__,
            )
        else:
            if self._bad(att.parsed, att.section, job.required):
                reason = "invalid"
        internal = internal_doc_ids(snapshot.chunks)
        sent = shown if remote.calls else []
        public_ids = [c.doc_id for c in sent if c.doc_id not in internal]
        internal_ids = [c.doc_id for c in sent if c.doc_id in internal]
        if reason is None and att is not None:
            writer = writer_record(
                provider=self.writer_provider,
                model=self.writer_model,
                public_doc_ids=public_ids,
                internal_doc_ids=internal_ids,
                calls=remote.calls,
            )
            return self._composed(job, att, writer)
        async with self.local_gate():  # 로컬 모델은 한 번에 하나 (FlockSlot)
            local = await self._attempt(self.llm, job)
        logger.warning(
            "compose.local_fallback section=%s reason=%s result=%s",
            key,
            reason,
            "failed" if self._bad(local.parsed, local.section, job.required) else "ok",
        )
        writer = writer_record(
            provider=self.local_provider,
            model=self.local_model,
            local_fallback=True,
            reason=reason,
            public_doc_ids=public_ids,
            internal_doc_ids=internal_ids,
            calls=remote.calls,
        )
        return self._composed(job, local, writer)

    @staticmethod
    def _composed(job: _Job, att: _Attempt, writer: dict[str, Any]) -> ComposedSection:
        digest = hashlib.sha256(f"{job.system}\x1f{job.instruction}".encode()).hexdigest()[:16]
        return ComposedSection(
            section=att.section,
            dropped=att.dropped,
            prompt_hash=digest,
            parse=att.parsed,
            ungrounded=att.lost,
            retries=att.retries,
            first_parse=att.first,
            writer=writer,
        )

    def _writer_chunks(self, key: str, snapshot: RetrievalSnapshot) -> list[Chunk]:
        """원격 작성에 보여 줄 청크 — 섹션 [자료] 와 같되, 전송 범위가 internal 제외면 뺀다."""
        chunks = self.chunks_for(key, snapshot)
        if self.writer_include_internal:
            return chunks
        internal = internal_doc_ids(snapshot.chunks)
        return [c for c in chunks if c.doc_id not in internal]

    # ── local_check ──────────────────────────────────────
    async def check_locally(
        self,
        sections: Sequence[Section],
        snapshot: RetrievalSnapshot,
        *,
        keys: set[str] | None = None,
    ) -> dict[str, Any]:
        """local_check — 근거 있는 문장을 로컬 모델이 지지|부분|불일치 로만 판정한다.

        섹션마다 LLM 1회, local_check_timeout 초 상한(슬롯 대기 시간은 빼고). 넘거나 실패·
        형식 오류면 그 섹션은 건너뛰고 skipped_sections 에 남긴다. keys 를 주면 그 섹션만
        본다(원격이 쓴 섹션)."""
        by_id: dict[str, Chunk] = {}
        for c in snapshot.chunks:
            by_id[c.chunk_id] = c
            by_id.setdefault(c.doc_id, c)
        checked: list[str] = []
        skipped: list[str] = []
        hashes: list[str] = []
        sentences = 0
        for sec in sections:
            if keys is not None and sec.key not in keys:
                continue
            prompt = local_check_prompt(sec, by_id)
            if prompt is None:
                continue
            async with self.local_gate():
                try:
                    raw = await asyncio.wait_for(
                        self.llm.complete(prompt, system=LOCAL_CHECK_SYSTEM, json_mode=True),
                        timeout=self.local_check_timeout,
                    )
                except Exception as exc:  # 시간 초과·서버 오류 — 그 섹션만 건너뛴다
                    skipped.append(sec.key)
                    logger.warning(
                        "compose.local_check_skipped section=%s error=%s",
                        sec.key,
                        type(exc).__name__,
                    )
                    continue
            verdicts = parse_local_check(raw, sec)
            if not verdicts:
                skipped.append(sec.key)
                continue
            checked.append(sec.key)
            sentences += len(verdicts)
            hashes.extend(mismatch_hashes(sec, verdicts))
        return {
            "enabled": True,
            "mismatches": len(hashes),
            "sentences": sentences,
            "checked_sections": checked,
            "skipped_sections": skipped,
            "mismatch_hashes": hashes,
        }

    def _validate(
        self,
        key: str,
        parsed: ParseResult,
        allowed_ids: set[str],
        req: ProposalRequest,
        snapshot: RetrievalSnapshot,
    ) -> tuple[Section, list[str], list[str]]:
        """파싱 결과 → 근거 범위(보안 A)·입력 고유명·본보기 인용 검증을 거친 섹션과 폐기 사유."""
        section, dropped = enforce_section_evidence(
            Section(key=key, sentences=parsed.sentences, choices=parsed.choices),
            allowed_ids,
            evidence_required=key in self.rules.evidence_required,
            evidence_forbidden=key in self.rules.evidence_forbidden,
        )
        section, lost = self._enforce_grounding(key, section, req)
        dropped.extend(lost)
        section, copied = self._enforce_no_exemplar(key, section, snapshot)
        dropped.extend(copied)
        return section, dropped, lost

    @staticmethod
    def _bad(parsed: ParseResult, section: Section, required: bool) -> bool:
        """실패 = 파싱 오류, 또는 필수 섹션인데 검증 뒤 문장이 0 (빈 목록·전부 폐기)."""
        return not parsed.ok or (required and not section.sentences)

    @staticmethod
    def _failure_reason(parsed: ParseResult, section: Section) -> str:
        if not parsed.ok:
            return parsed.status
        return "dropped" if parsed.sentences and not section.sentences else "empty"

    @staticmethod
    def _hint(parsed: ParseResult, dropped: Sequence[str], *, choice_section: bool) -> str:
        if not parsed.ok:
            return correction_hint(parsed, choice_section=choice_section)
        if parsed.sentences and dropped:  # 전부 폐기 — 폐기 사유를 그대로 알려 준다
            return dropped_hint(dropped)
        return EMPTY_HINT

    def _fallback_chunks(self, key: str, snapshot: RetrievalSnapshot) -> list[Chunk]:
        """대체 작성에 보여 줄 청크 — 섹션 [자료] 와 같되, 검토 정책이 internal 제외면 뺀다."""
        chunks = self.chunks_for(key, snapshot)
        if self.fallback_include_internal:
            return chunks
        internal = internal_doc_ids(snapshot.chunks)
        return [c for c in chunks if c.doc_id not in internal]

    def _parse(
        self, key: str, raw: str, spec: ChoiceSpec | None, options: dict[str, dict[str, str]]
    ) -> ParseResult:
        if spec is not None:
            return parse_choice_section(raw, options.get(key, {}), min_n=spec.min, max_n=spec.max)
        return parse_sentences(raw)

    def _prompt(
        self,
        key: str,
        instruction: str,
        req: ProposalRequest,
        snapshot: RetrievalSnapshot,
        options: dict[str, str] | None,
        *,
        outline: Outline | None = None,
        candidate: Section | None = None,
        notes: Mapping[str, str] | None = None,
        keep: Sequence[str] = (),
        compact: bool = False,  # 형식 교정 재요청용 — 설계도·본보기·후보 없이 기본 지시만
        chunks: list[Chunk] | None = None,  # 대체 작성: 전송 범위를 적용한 [자료] 를 직접 준다
        exemplars: bool = True,  # 원격 작성 전송 범위가 internal 제외면 본보기(사내 과제)를 뺀다
    ) -> str:
        parts = [
            f"[섹션: {key}]\n{instruction}",
            f"[제안 입력]\n{json.dumps(req.prompt_view(), ensure_ascii=False)}",
        ]
        prose = options is None and key != "title"  # 제목·선택형은 설계 요약·본보기를 넣지 않는다
        if outline is not None and prose:  # Q2 설계도 — 앱이 검증한 값(근거 id 는 검색 집합 안)
            plan = outline.plan(key)
            if plan is not None:
                parts.append(
                    f"[이 섹션의 설계 — 핵심 메시지를 따라 쓴다]\n{plan.message}\n"
                    f"우선 근거: {', '.join(plan.evidence) or '(지정 없음)'}\n"
                    f"연결 섹션: {', '.join(plan.links) or '(없음)'}"
                )
            summary = outline.summary_text()
            if summary:
                parts.append(f"[전체 설계 요약 — 섹션 간 일관성 유지]\n{summary[:600]}")
        exemplar_rows = "" if compact or not exemplars else self._exemplar_rows(key, snapshot)
        if exemplar_rows:  # Q4 본보기 — 구성·문체만. doc id 는 주지 않는다 (근거로 못 달게)
            parts.append(
                "[본보기 — 채택된 과제의 같은 항목 문장. 구성·문체·분량만 참고하고 내용·수치·"
                "고유명은 절대 가져오지 않는다. 근거(evidence)로 쓰지 않는다]\n" + exemplar_rows
            )
        if candidate is not None:  # Q7 후보 B
            listed = "\n".join(f"- {s.text}" for s in candidate.sentences)
            parts.append(
                "[후보 B 작성] 이 섹션의 두 번째 후보를 쓴다. 아래 후보 A 와 다른 전개 순서·다른 "
                "근거 우선으로 쓰고, A 의 문장을 되풀이하지 않는다. 같은 형식으로 출력한다.\n"
                f"후보 A:\n{listed}"
            )
        if notes:  # U3 보완 질문에 대한 제안자 답 — 제안자 입력과 같은 신뢰 수준
            parts.append(
                "[제안자 보완 메모 — 제안자가 보완 질문에 답한 내용. 반영한다]\n"
                + json.dumps(dict(notes), ensure_ascii=False)
            )
        if keep:  # U3 다시 쓰기: 제안자가 고친 문장은 앱이 보존한다 — 중복해서 쓰지 않는다
            parts.append(
                "[보존 문장 — 제안자가 직접 쓴 문장. 앱이 그대로 둔다. 같은 내용을 다시 쓰지 말 것]"
                "\n" + json.dumps(list(keep), ensure_ascii=False)
            )
        if self.schedule_metrics:  # U6
            period = research_period_months(req.constraints)
            if period is not None and key == SCHEDULE_SECTION:
                parts.append(schedule_instruction(period))
            if period is not None and key in METRIC_SECTIONS:
                parts.append(metric_instruction())
        # 선택지·판정표는 앱이 만든 값이다 (비신뢰 구획 밖). 문서 제목은 넣지 않는다.
        if options is not None:
            listed = "\n".join(f"- {oid}: {label}" for oid, label in options.items())
            parts.append(f"[선택지 — 이 id 중에서만 고른다]\n{listed}")
            # 정답 모양 예시 1개. 값은 가상(선택지에 없는 id, 형식만 보이는 근거 id)이라 그대로 쓰면
            # 선택지 대조·근거 대조에서 걸려 폐기된다.
            parts.append(
                "[출력 모양 예시 — 모양만 참고. 값은 가상이며 그대로 쓰면 폐기됨]\n"
                + CHOICE_EXAMPLE
            )
        if key in DIFFERENTIATION_SECTIONS and req.differentiation:
            parts.append(
                "[제안자가 정한 차별화 방향 — 유사과제와의 차이를 이 방향으로 서술한다]\n"
                + req.differentiation
            )
        if key == OVERLAP_SECTION and snapshot.overlap_checked:
            rows = "\n".join(
                f"- id={a.doc_id} 구분={a.tier} 유사도={a.similarity:.2f} "
                f"중복기준초과={'예' if a.blocking else '아니오'} basis={a.basis or '-'} "
                f"겹친키워드={','.join(a.keywords) or '-'}"
                + (" 제안자판단=유사함(차별성을 쓸 대상)" if a.choice == "similar" else "")
                for a in snapshot.overlap
            )
            parts.append(f"[유사과제 판정 — 앱 계산]\n{rows}")
        if key in self.rules.evidence_forbidden:
            # 자료 인용 금지 섹션에 자료를 주면 약한 모델은 그래도 인용한다 → 아예 주지 않는다.
            parts.append(
                "[자료]\n(없음 — 이 섹션은 제안자 입력만 근거로 쓴다. evidence 는 빈 배열)"
            )
        else:
            shown = self.chunks_for(key, snapshot) if chunks is None else chunks
            parts.append(f"[자료]\n{wrap_untrusted(shown)}")
        return "\n\n".join(parts)

    def chunks_for(self, key: str, snapshot: RetrievalSnapshot) -> list[Chunk]:
        """섹션 프롬프트 [자료] — 섹션별 검색 결과(또는 전체)에 근거 구성 규칙(허용 doc_type)과
        길이 상한(chunk_max_chars; 섹션별 검색이 없는 섹션은 base_chunk_limit 개)을 적용."""
        chunks = snapshot.chunks_for(key)
        if self.mix is not None and snapshot.doc_types:
            chunks = self.mix.filter(key, chunks, snapshot.doc_types)
        limit = 0 if snapshot.section_chunks.get(key) else self.base_chunk_limit
        return clip_chunks(chunks, max_chars=self.chunk_max_chars, limit=limit)

    @staticmethod
    def _exemplar_rows(key: str, snapshot: RetrievalSnapshot) -> str:
        rows: list[str] = []
        for i, ex in enumerate(snapshot.exemplars, 1):
            sections = ex.get("sections") if isinstance(ex, dict) else None
            texts = (sections or {}).get(key) if isinstance(sections, dict) else None
            for t in texts or []:
                if isinstance(t, str) and t.strip():
                    rows.append(f"- (본보기 {i}) {escape_untrusted(t)}")
        return "\n".join(rows)

    def _enforce_no_exemplar(
        self, key: str, section: Section, snapshot: RetrievalSnapshot
    ) -> tuple[Section, list[str]]:
        """Q4 인용 금지 검증 — 본보기 문장을 그대로 쓴 문장은 폐기한다.

        본보기 과제가 검색 근거에도 들어 있으면 그 doc 을 근거로 인용하는 것은 막지 않는다 — 가장
        관련 있는 사내 기록이라 막으면 문장이 통째로 사라진다(2026-10-27 측정 2단계에서 title·
        overlap_review 까지 빈칸이 되어 invalid). 본보기 id 는 프롬프트에 주지 않으므로 "본보기로서"
        인용할 길은 없다."""
        if not snapshot.exemplars:
            return section, []
        copied = {
            _norm_text(t)
            for ex in snapshot.exemplars
            for texts in (ex.get("sections") or {}).values()
            for t in texts
            if isinstance(t, str)
        }
        kept: list[Sentence] = []
        dropped: list[str] = []
        for s in section.sentences:
            if _norm_text(s.text) in copied:
                dropped.append(f"{key}: {EXEMPLAR_DROP} → 폐기: {s.text[:40]}")
                continue
            kept.append(s)
        return section.model_copy(update={"sentences": kept}), dropped

    def _enforce_grounding(
        self, key: str, section: Section, req: ProposalRequest
    ) -> tuple[Section, list[str]]:
        sources = self.rules.input_grounded.get(key)
        if not sources:
            return section, []
        allowed: list[str] = []
        for name in sources:
            if name == STRATEGY_SOURCE:
                allowed.extend(self.strategy.names())
                allowed.extend(self.strategy.options())  # id 도 허용
            else:
                value = getattr(req, name, "")
                allowed.append(value if isinstance(value, str) else "")
        kept: list[Sentence] = []
        dropped: list[str] = []
        for s in section.sentences:
            missing = ungrounded(s.text, allowed)
            if missing:
                dropped.append(f"{key}: 입력에 없는 고유명 {missing[:3]} → 폐기: {s.text[:40]}")
                continue
            kept.append(s)
        return section.model_copy(update={"sentences": kept}), dropped

    # ── finalize ─────────────────────────────────────────
    def style_problems(self, req: ProposalRequest, sections: list[Section]) -> list[LintProblem]:
        """Q6 규칙 검사 알림만(고치지 않음) — 편집·검토 반영으로 새 버전이 생길 때도 알림을 유지."""
        if not self.rule_check:
            return []
        result = style.check_sections(
            sections, constraints=req.constraints, max_chars=self.max_sentence_chars, fix=False
        )
        return [
            LintProblem(
                section=f.section,
                code=f.code,
                message=f.message,
                severity="warning",
                sentence=f.sentence,
            )
            for f in result.findings
        ]

    def finalize(
        self,
        run_id: str,
        req: ProposalRequest,
        snapshot: RetrievalSnapshot,
        sections: list[Section],
    ) -> tuple[Draft, list[LintProblem]]:
        """규칙 검사(Q6: 어미 통일·완전 중복 제거는 고치고, 긴 문장·문체 혼용·연차 불일치는 경고)
        + lint. 돌려주는 Draft 의 sections 가 정리된 문장이다 (호출자는 이것을 저장한다)."""
        trimmed: list[LintProblem] = []
        if self.rule_check:
            sections = style.check_sections(
                sections, constraints=req.constraints, max_chars=self.max_sentence_chars
            ).sections
            sections, cuts = style.trim_sections(sections, self.rules.max_chars)
            trimmed = [
                LintProblem(section=f.section, code=f.code, message=f.message, severity="warning")
                for f in cuts
            ]
        draft = Draft(
            run_id=run_id,
            request=req,
            sections=sections,
            retrieved_ids=snapshot.retrieved_ids,
            template=self.template,
        )
        return draft, [*self.lint_draft(draft, snapshot), *trimmed]

    def lint_draft(self, draft: Draft, snapshot: RetrievalSnapshot | None) -> list[LintProblem]:
        """규칙 검사 전부 — lint(rules.yaml) + Q6 문체·길이·연차 경고 + U6 일정 초과 경고.
        생성(finalize)과 버전 저장이 같은 판정을 쓴다."""
        chunk_texts = {c.chunk_id: c.text for c in snapshot.chunks} if snapshot else {}
        problems = lint(
            draft,
            self.rules,
            choice_options=self.choice_options(),
            chunk_texts=chunk_texts,
            evidence_skipped=self.evidence_skipped(snapshot) if snapshot else None,
            facts=snapshot.facts if snapshot else None,
        )
        problems.extend(self.style_problems(draft.request, draft.sections))
        if self.schedule_metrics:
            problems.extend(schedule_problems(draft))
        return problems

    async def __call__(self, req: ProposalRequest) -> Draft:
        snapshot = await self.retrieve_sections(req, await self.retrieve(req))
        sections: list[Section] = []
        dropped: list[str] = []
        for key in self.section_keys:
            composed = await self.compose_section(key, req, snapshot)
            sections.append(composed.section)
            dropped.extend(composed.dropped)
        draft, problems = self.finalize(uuid.uuid4().hex[:12], req, snapshot, sections)
        if has_errors(problems):
            raise DraftInvalid(problems, dropped)
        return draft


def internal_doc_ids(chunks: Sequence[Chunk]) -> set[str]:
    return {c.doc_id for c in chunks if c.visibility == "internal"}


def _norm_text(text: str) -> str:
    return "".join(ch for ch in text if not ch.isspace() and ch not in ".。,")
