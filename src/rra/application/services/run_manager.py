"""생성 실행 관리자 — 상태 저장, 중단 후 재개, 단계별 진행 기록, 동시성 1.

모든 진입점(CLI·MCP, 이후 REST)이 이 클래스로만 생성한다.

- 재개 단위는 step: retrieve(1회, 스냅샷 저장) → section:<key>(LLM 1회씩) → finalize(lint).
  이미 저장된 step 은 건너뛴다. 검색은 재개 때 다시 하지 않는다 (근거 집합 고정).
- 섹션은 근거 검증을 통과한 뒤에만 저장된다 → 부분 초안도 항상 인용 규칙을 만족한다.
- 백그라운드 실행은 TaskRunner 포트로만 띄운다 (asyncio 를 직접 쓰지 않는다). 진입점마다 루프가
  달라도(CLI·UI 워커·REST) 조립에서 맞는 구현을 끼운다.
- 동시성: run 락(claim) → 전역 슬롯(slot) 순서로 잡는다. 둘 다 프로세스 간 락이라
  CLI 와 MCP 서버가 동시에 생성하지 않고, 락을 잡은 프로세스가 죽으면 run 은 interrupted 가 된다.
- manifest(보안 I): 해시·id·개수·예외 클래스명만. 제안 입력·문장·오류 메시지는 넣지 않는다.
- 양식 개정: run 은 생성 때의 양식 id(state.template)와 섹션 순서(state.steps)를 기억한다.
  현재 양식과 다른 run(legacy)은 조회만 되고 재개·확정은 거부한다. 섹션 키를 자동 변환하지 않는다
  — 섹션의 의미·근거 규칙이 달라 변환하면 양식에 맞지 않는 글이 새 양식처럼 보인다.
- 선택형 섹션(과제유형·활용계획·전략)은 LLM 제안(Section.choices)과
  사용자 확정(confirm)을 따로 둔다.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from rra.application.ports import (
    GenerationSlot,
    RendererPort,
    RunBusy,
    RunClaim,
    RunLogPort,
    RunNotFound,
    RunStorePort,
    TaskRunner,
)
from rra.application.ports.auth import BudgetExhausted, DailyBudgetPort
from rra.application.ports.renderer import RenderRejected
from rra.application.usecases.figures import FigureBuild, MakeFigures, SpecRejected
from rra.application.usecases.generate_proposal import CORE_SECTIONS, GenerateProposal
from rra.application.usecases.outline import OutlineSections
from rra.application.usecases.render_check import RenderCheck, render_check
from rra.application.usecases.review_draft import ReviewContext, ReviewDraft
from rra.application.usecases.submit_check import SubmitCheck, submit_check
from rra.domain.models import (
    Annotation,
    Confirmation,
    Draft,
    DraftVersion,
    PipelineConfig,
    ProposalRequest,
    ProposerInfo,
    RecommendationResult,
    RetrievalSnapshot,
    ReviewComment,
    ReviewRound,
    RunState,
    Satisfaction,
    Section,
    Sentence,
    StepRecord,
    UsabilityConfig,
    UsageRecord,
)
from rra.domain.models.figure import (
    Figure,
    FigureChange,
    FigurePlacement,
    FigureRecommendation,
    TechniqueOutcome,
)
from rra.domain.models.outline import Outline
from rra.domain.models.review import (
    EditRequest,
    EvidenceDecisionRequest,
    parse_sentence_id,
    sentence_id,
)
from rra.domain.models.run import (
    ACTIVE,
    DRAFT_REVIEW,
    FIGURES,
    FINALIZE,
    FINISHED,
    OUTLINE,
    RESUMABLE,
    RETRIEVE,
    is_valid_run_id,
    plan_steps,
    section_step,
)
from rra.domain.rules import draft_failures, review_flow
from rra.domain.rules import figures as figure_rules
from rra.domain.rules.auth_policy import daily_limit_reached
from rra.domain.rules.checklist import clean_answers, coverage, missing_elements
from rra.domain.rules.evidence import (
    DecisionRejected,
    apply_decisions,
    basis_label,
    bulk_approvals,
    decisions_for_sections,
    evidence_attention,
    evidence_counts,
    excerpt,
    exclusion_problems,
    needs_check,
    support_problems,
)
from rra.domain.rules.lint import has_errors
from rra.domain.rules.llm_output import clean_sentence
from rra.domain.rules.overlap import SOURCE_LABELS
from rra.domain.rules.request_change import (
    FIELD_LABELS,
    MODE_NOTES,
    affected_sections,
    changed_fields,
    regen_targets,
)
from rra.domain.rules.review_flow import InvalidTransition
from rra.domain.rules.rewrite import REWRITE_NOTE, pick, side_by_side
from rra.domain.rules.run_title import draft_title
from rra.domain.rules.usage import refresh as refresh_usage
from rra.domain.rules.usage import step_durations as usage_step_durations
from rra.domain.rules.usage import total_seconds as usage_total_seconds
from rra.domain.rules.versions import (
    changed_sections,
    count_changed_sentences,
    diff_versions,
    reorder,
    same_content,
    section_from_texts,
    split_sentences,
)
from rra.domain.rules.writer import (
    SELF_REVIEW,
    gemini_calls,
    local_check_problems,
    local_check_view,
    local_sections,
)

logger = logging.getLogger("rra.runs")

StepCallback = Callable[[RunState, StepRecord], None]

__all__ = [
    "Citation",
    "ConfirmRejected",
    "DraftView",
    "EvidenceItem",
    "FeatureDisabled",
    "FeedbackRejected",
    "RewriteRejected",
    "RewriteView",
    "QueueFull",
    "RunBusy",
    "RunManager",
    "RunNotFound",
    "RunNotResumable",
]


class DailyLimitReached(RuntimeError):
    """사용자별 일일 생성 상한 (레인 A: 공용 계정 10건·직원 20건)."""


class ReviewBudgetExhausted(RuntimeError):
    """외부 검토 LLM 일일 전체 상한 초과 — 검토 없이 진행한다."""


class QueueFull(RuntimeError):
    """대기·실행 중인 run 이 상한에 닿았다."""


class RunNotResumable(RuntimeError):
    """interrupted 상태가 아니거나, 양식 개정 전 run 이라 재개할 수 없다."""


class RenderUnavailable(RuntimeError):
    """렌더러가 조립되지 않았다 (python-hwpx 미설치 등)."""


class ConfirmRejected(ValueError):
    """선택값 확정 요청이 규칙(선택지 목록·개수·run 상태)에 맞지 않는다."""


class EditRejected(ValueError):
    """편집·되돌리기 요청이 규칙(상태·문장 id·수정안 검증 통과 여부)에 맞지 않는다."""


class FinalizeRejected(ValueError):
    """최종 마무리 조건(최종 검토 완료 또는 건너뜀, 검토 중 아님, 임시 편집 없음)에 맞지 않는다."""


class VersionConflict(EditRejected):
    """저장 요청의 base_version 과 현재 버전이 다르다 (그 사이 다른 버전이 생김) — 409."""


class WorkingRejected(ValueError):
    """임시 저장은 편집 가능한 상태에서만 (검토 중·생성 중 불가)."""


class FeatureDisabled(RuntimeError):
    """config/usability.yaml 에서 꺼진 기능."""


class RewriteRejected(ValueError):
    """다시 쓰기·후보 반영 요청이 규칙(상태·섹션·후보 유무)에 맞지 않는다."""


class FeedbackRejected(ValueError):
    """만족도 기록은 마무리(finalized) 뒤에만."""


@dataclass(frozen=True)
class EvidenceItem:
    """U1 문장 하나의 근거 하나 — 원문 발췌 + 문서 메타 + 적합성 판정 + 제안자 판단."""

    evidence_id: str
    doc_id: str
    chunk_id: str | None
    text: str  # 발췌 (비신뢰)
    title: str | None  # 비신뢰
    source: str
    source_label: str
    orgs: list[str]
    year: int | None
    ingested_at: str | None
    basis: str | None
    basis_label: str
    needs_check: bool
    support: str | None  # 지지|부분|불일치 (Argon 1차 검토)
    decision: str | None  # approve|replace|exclude (제안자)
    in_snapshot: bool
    url: str | None = None  # 원본 링크 — 이미지 판독이면 이미지 URL(raw.image.url), 아니면 문서 URL


@dataclass(frozen=True)
class RewriteView:
    section: str
    current: Section
    candidate: Section
    rows: list[dict]
    dropped: list[str]
    created_at: str | None


@dataclass(frozen=True)
class RegenerateResult:
    """항목 17 — 입력 변경 뒤 다시 쓰기 결과. version 은 새 버전(바뀐 섹션이 없으면 현재 버전)."""

    version: DraftVersion
    mode: str
    fields: list[str]
    regenerated: list[str]  # 새로 쓴 섹션
    failed: list[dict[str, str]]  # 다시 쓰지 못해 이전 내용을 둔 섹션 {key, reason}
    kept: list[str]  # 앱이 쓰는 섹션 등 그대로 둔 섹션
    saved_only: bool = False  # 양식 칸(제안부서·예산)만 바뀌어 입력만 저장했다


@dataclass(frozen=True)
class FinalizeResult:
    data: bytes  # HWPX
    confirmation: Confirmation
    check: RenderCheck
    version: int
    state: RunState
    title: str = ""  # 내려받기 파일 이름용 연구과제명 (그 버전의 1-가, 없으면 가제)
    hwpx_format: dict[str, Any] | None = None  # 항목 12 서식 점검 결과 (건수만)


LEGACY_HINT = (
    "이전 양식으로 만든 run 입니다 — rra generate --reuse-input {run_id} 로 새로 생성하십시오."
)


@dataclass(frozen=True)
class Citation:
    id: str  # 문장 evidence 에 적힌 id (chunk_id 또는 doc_id)
    doc_id: str
    title: str | None  # 수집 문서 제목 — 비신뢰 텍스트


@dataclass(frozen=True)
class DraftView:
    """완료된 섹션만 모은 (부분) 초안 + 상태."""

    state: RunState
    sections: list[Section]
    citations: list[Citation] = field(default_factory=list)
    legacy: bool = False  # 양식 개정 전 run (조회만 가능)
    confirmation: Confirmation | None = None
    # 선택형 섹션 → {선택지 id: 표시 이름}. legacy 면 비어 있다
    choice_options: dict[str, dict[str, str]] = field(default_factory=dict)
    version: int = 1  # 보고 있는 초안 버전
    versions: list[int] = field(default_factory=list)
    review: ReviewRound | None = None  # 최신 검토 차수 (없으면 None)
    reviews: list[int] = field(default_factory=list)
    has_working: bool = False  # 저장하지 않은 임시 편집(draft_working.json)이 있다
    strategy_status: str = "confirmed"  # draft 면 화면·API 에 "전략체계 초안(확인 전)" 표시
    figures: list[Figure] = field(default_factory=list)  # [G] 보고 있는 버전의 그림 목록


def _utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _cleaned(section: Section) -> Section:
    """문장 텍스트만 정리(clean_sentence). 개수·순서·근거·origin 은 그대로(lint 인덱스 유지)."""
    return section.model_copy(
        update={
            "sentences": [
                s.model_copy(update={"text": clean_sentence(s.text)}) for s in section.sentences
            ]
        }
    )


class RunManager:
    def __init__(
        self,
        generate: GenerateProposal,
        store: RunStorePort,
        slot: GenerationSlot,
        run_log: RunLogPort,
        runner: TaskRunner,
        *,
        max_queued: int = 3,
        model: str | None = None,
        clock: Callable[[], str] = _utcnow,
        renderer: RendererPort | None = None,
        line_limits: Mapping[str, int] | None = None,
        reviewer: ReviewDraft | None = None,
        review_auto: bool = True,
        pipeline: PipelineConfig | None = None,
        outliner: OutlineSections | None = None,
        usability: UsabilityConfig | None = None,
        checklists: Mapping[str, list[dict[str, Any]]] | None = None,
        generate_public: GenerateProposal | None = None,
        review_budget: DailyBudgetPort | None = None,
        figures: MakeFigures | None = None,
        run_slot: GenerationSlot | None = None,
        first_pass: bool = True,
        live_search: Any | None = None,
    ):
        # [4] 실시간 자료 검색(LiveSearch, ADR 0031) — None 이면 종전 동작(DB 만)
        self.live_search = live_search
        self.usability = usability or UsabilityConfig()  # U1~U8 켜기/끄기
        # Argon 작성(ADR 0032)일 때 run 전체가 잡는 N칸 슬롯(runs.max_concurrent).
        # None 이면 칸 제한 없음
        self.run_slot = run_slot
        # llm.yaml review.first_pass — False 면 ③ Argon 1차 검토를 자동으로 돌리지 않는다(자기 검토)
        self.first_pass = first_pass
        self.figures = figures  # [G] 그림 유스케이스 (None 이면 그림 단계 없음)
        # 공용 계정 run(scope=public)용 — internal 을 뺀 저장소로 조립된 같은 유스케이스
        self.generate_public = generate_public
        self.review_budget = review_budget  # 외부 검토 LLM 일일 상한 (None 이면 상한 없음)
        self.checklists: dict[str, list[dict[str, Any]]] = dict(checklists or {})
        self.generate = generate
        self.reviewer = reviewer  # None 이면 검토를 건너뛴다 (review_skipped)
        self.outliner = outliner  # Q2 섹션 설계도 (pipeline.outline 이 켜져 있을 때만 조립)
        self.review_auto = review_auto
        self.pipeline = pipeline or PipelineConfig()  # ③ 단계 켜기/끄기 (config/pipeline.yaml)
        self._review_tasks: dict[str, str] = {}  # run_id → 실행 중 검토 작업 key (차수별 고유)
        self.line_limits: dict[str, int] = dict(line_limits or {})  # slots.yaml 한 줄 칸 상한
        self.store = store
        self.slot = slot
        self.run_log = run_log
        self.runner = runner
        self.renderer = renderer
        self.max_queued = max_queued
        self.model = model
        self._clock = clock

    # ── 제출·재개 ─────────────────────────────────────────
    async def submit(
        self,
        user: str,
        req: ProposalRequest,
        *,
        on_step: StepCallback | None = None,
        differentiation: dict[str, Any] | None = None,
        recommendations: RecommendationResult | None = None,
        chosen_recommendation: int | None = None,
        priority_evidence: list[str] | None = None,
        scope: str = "all",
        daily_limit: int | None = None,
        idea_versions: list[Any] | None = None,
    ) -> RunState:
        """queued 로 저장하고 백그라운드 실행을 시작한 뒤 즉시 돌려준다.

        idea_versions: ② 차별화 과제안 버전(IdeaVersion — 원래 아이디어·고른 카드·직접 고친 안).
        칸 거르기·개인정보 표식 뒤 run 의 idea_versions.json 에 복사한다 (레인 A).

        scope: "public" 이면 검색·근거에서 visibility=internal 을 뺀다 (공용 계정).
        daily_limit: 이 사용자의 오늘 생성 건수 상한 (None 이면 없음). 넘으면 DailyLimitReached.

        priority_evidence: U5 브리핑에서 고른 우선 근거 id — retrieve 뒤 검색 집합 안의 것만
        snapshot.priority_ids 에 남기고 그 청크를 앞세운다 (proposer_notes.json 에 보관).

        differentiation: 기능 2 차별화 제안의 전송 기록(DifferentiationProposal.transfer()).
        manifest 에만 남는다.
        recommendations: 차별화 과제 추천 결과 — 전체는 run 의 recommendations.json 에 복사하고
        manifest 에는 전송 기록 + 고른 추천 index(chosen) 만 남긴다.
        """
        mine = self.list_runs(user, limit=1000)
        active = [s for s in mine if s.status in ACTIVE]
        if len(active) >= self.max_queued:
            raise QueueFull(
                f"대기·실행 중인 생성이 {len(active)}건입니다 (상한 {self.max_queued})."
            )
        today = self._clock()[:10]
        if daily_limit_reached([s.created_at for s in mine], today, daily_limit):
            raise DailyLimitReached(f"오늘 생성 상한 {daily_limit}건에 이르렀습니다.")
        state = self.store.create(user, req, self._plan(), self._clock())
        state.scope = "public" if scope == "public" else "all"
        state.writer = "gemini" if self._generate_for(state).writes_remotely else "local"
        state.model = self.model
        state.template = self.generate.template
        state.differentiation = dict(differentiation) if differentiation else None
        if recommendations is not None:
            self.store.save_recommendations(
                user, state.run_id, recommendations.model_dump(mode="json")
            )
            state.recommendations = {
                **recommendations.transfer(),
                "chosen": chosen_recommendation,
            }
        if priority_evidence:
            ids = [str(x)[:200] for x in priority_evidence if str(x).strip()][:50]
            self.store.save_notes(user, state.run_id, {"priority_evidence": ids})
        if idea_versions:
            from rra.domain.rules.idea_plan import normalize_versions

            saver = getattr(self.store, "save_idea_versions", None)
            if saver is not None:
                saver(user, state.run_id, normalize_versions(idea_versions))
        self.store.save_state(state)
        claim = self.store.claim(user, state.run_id)  # 백그라운드 시작 전에 잡아 공백을 없앤다
        self._start(state, claim, on_step)
        self._record(state)
        return state

    async def resume(
        self, user: str, run_id: str, *, on_step: StepCallback | None = None
    ) -> RunState:
        state = await self.status(user, run_id)
        if self.is_legacy(state):
            raise RunNotResumable(LEGACY_HINT.format(run_id=run_id))
        if state.status not in RESUMABLE:
            raise RunNotResumable(f"{state.status} 상태의 run 은 재개할 수 없습니다.")
        claim = self.store.claim(user, run_id)  # 다른 프로세스가 이미 이어서 돌리면 RunBusy
        state.status = "queued"
        state.updated_at = self._clock()
        self.store.save_state(state)
        self._start(state, claim, on_step)
        self._record(state)
        return state

    async def wait(self, user: str, run_id: str) -> RunState:
        """같은 프로세스에서 시작한 run(생성·자동 검토)이 끝날 때까지 기다린다 (CLI 용)."""
        if self.runner.is_running(run_id):
            await self.runner.wait(run_id)
        key = self._review_tasks.get(run_id)
        if key and self.runner.is_running(key):
            await self.runner.wait(key)
        return await self.status(user, run_id)

    def cancel(self, user: str, run_id: str) -> bool:
        """같은 프로세스에서 돌고 있는 run 을 취소한다. 상태는 interrupted 로 남아 재개 가능."""
        if not is_valid_run_id(run_id) or not self.runner.is_running(run_id):
            return False
        self.store.load_state(user, run_id)  # 다른 사용자의 run 이면 RunNotFound
        return self.runner.cancel(run_id)

    def _start(self, state: RunState, claim: RunClaim, on_step: StepCallback | None) -> None:
        self.runner.submit(state.run_id, self._execute(state.user, state.run_id, claim, on_step))

    # ── 실행 ─────────────────────────────────────────────
    async def _execute(
        self, user: str, run_id: str, claim: RunClaim, on_step: StepCallback | None
    ) -> RunState:
        state = self.store.load_state(user, run_id)
        current: StepRecord | None = None
        auto_review = False
        gen = self._generate_for(state)
        try:
            # 로컬 작성: run 전체가 전역 슬롯 1칸 안에서. Argon 작성(ADR 0032): run 은
            # run_slot(최대 runs.max_concurrent)만 잡고, 로컬 모델 단계(대체 작성·local_check·
            # 설계도)만 전역 슬롯을 잡는다
            async with self._run_gate(gen):
                state.status = "running"
                self._save(state)
                try:
                    req = self.store.load_request(user, run_id)
                except ValidationError:
                    state.status = "failed"  # 저장된 입력이 깨짐 — 재개해도 소용없다
                    return state

                snapshot = self.store.load_snapshot(user, run_id)
                if snapshot is None:
                    await self._live_step(user, state, req)
                    current = self._begin(state, RETRIEVE)
                    snapshot = await gen.retrieve(req)
                    snapshot = self._prioritize(user, run_id, snapshot)
                    self.store.save_snapshot(user, run_id, snapshot)
                    self._finish(
                        state,
                        current,
                        on_step,
                        evidence=sorted(snapshot.retrieved_ids),
                        dropped=len(snapshot.dropped_chunks),  # 관련도 하한 탈락 청크 수
                    )
                    current = None
                self._ensure_done(state, RETRIEVE)

                outline_gate = (  # Q2 설계도 = 로컬 모델 (켜져 있을 때만 슬롯)
                    self._local_gate(gen)
                    if self.pipeline.outline and self.outliner is not None
                    else contextlib.nullcontext()
                )
                async with outline_gate:
                    outline = await self._outline_step(user, run_id, state, req, snapshot, on_step)
                if self.pipeline.section_search and not snapshot.section_chunks:
                    snapshot = await gen.retrieve_sections(req, snapshot, outline)
                    self.store.save_snapshot(user, run_id, snapshot)  # 재개 때 다시 하지 않는다

                sections = self.store.load_sections(user, run_id)
                await self._compose_sections(
                    user, run_id, state, gen, req, snapshot, outline, sections, on_step
                )

                current = self._begin(state, FINALIZE)
                ordered = [sections[k] for k in self.generate.section_keys]
                draft, problems = self.generate.finalize(run_id, req, snapshot, ordered)
                fixed = _auto_fixed(ordered, draft.sections)  # Q6 자동 정리한 문장 수
                if fixed:
                    for sec in draft.sections:
                        self.store.save_section(user, run_id, sec)
                ordered = draft.sections
                self.store.save_draft(user, run_id, draft)
                if gen.local_check and gen.writes_remotely:
                    # 로컬 근거 대조 — Argon 이 쓴 섹션만, 섹션당 시간 상한. 불일치는 경고(알림)만
                    remote_keys = {
                        k for k, w in state.writers.items() if not w.get("local_fallback")
                    }
                    state.local_check = await gen.check_locally(ordered, snapshot, keys=remote_keys)
                    problems = [*problems, *local_check_problems(ordered, state.local_check)]
                # 빈 초안 금지(ADR 0027): 실패 섹션은 빈칸 + 목록·사유, 전부 실패일 때만 invalid
                failed = draft_failures.failed_sections(
                    state.steps, self.generate.rules.required_sections
                )
                problems = draft_failures.relax_failed(problems, failed)
                state.failed_sections = failed
                state.problems = [p.model_dump() for p in problems]
                self._touch_usage(user, run_id, state)
                invalid = has_errors(problems) or draft_failures.all_failed(
                    failed, draft_failures.attempted_sections(state.steps)
                )
                if failed:
                    logger.warning(
                        "run.sections_failed run=%s failed=%s invalid=%s",
                        run_id,
                        ",".join(f"{f.key}:{f.reason}" for f in failed),
                        invalid,
                    )
                if not invalid:  # draft_v1 = 첫 작성 (로컬 또는 Argon)
                    self.store.save_version(
                        user,
                        run_id,
                        DraftVersion(
                            version=1,
                            origin="local",
                            sections=ordered,
                            created_at=self._clock(),
                            changed_sections=[s.key for s in ordered],
                            alerts=len(problems),
                        ),
                    )
                    state.draft_version = 1
                self._finish(state, current, on_step, dropped=fixed)
                current = None
                if not invalid and self.figures is not None:
                    # [G] 그림 — v1 에 붙인다(검토 전). 그동안 상태는 running 그대로. drafted 로
                    # 먼저 저장하면 화면이 편집을 열고 편집은 이 실행의 락에 막힌다(10-28 시험)
                    # 그림 명세는 Argon 먼저(#70) — 이미지 생성까지 전역 슬롯을 잡으면 동시 run 이
                    # 그림 단계에서 줄을 선다. 명세의 로컬 대체는 그림 유스케이스 몫(레인 A)
                    await self._figures_step(user, run_id, state, ordered, req, snapshot)
                state.status = "invalid" if invalid else "drafted"
                if not invalid:
                    wants_review = self.pipeline.draft_review and self.review_auto
                    if wants_review and self.reviewer is None:
                        self._skip_review(user, run_id, state, "no_review_llm")
                    elif wants_review and self._budget_exhausted():
                        self._skip_review(user, run_id, state, "budget")
                    elif wants_review and not self.first_pass:
                        # Argon 이 쓴 초안을 Argon 이 1차 검토하면 자기 검토 — 끈다
                        # (⑤ 최종 검토는 그대로)
                        self._skip_review(user, run_id, state, SELF_REVIEW)
                        wants_review = False
                    elif not wants_review:
                        self._skip_review(user, run_id, state, "disabled")
                    auto_review = (
                        wants_review and self.reviewer is not None and not self._budget_exhausted()
                    )
                return state
        except Exception as exc:  # 어떤 실패든 저장된 step 은 남고, 재개로 이어서 한다
            self._interrupt(state, current, type(exc).__name__)
            logger.warning("run.interrupted run=%s error=%s", run_id, type(exc).__name__)
            return state
        except BaseException as exc:  # 취소(CancelledError 는 BaseException) — 상태만 남기고 전파
            self._interrupt(state, current, type(exc).__name__)
            raise
        finally:
            state.updated_at = self._clock()
            self._save(state)
            claim.release()
            if auto_review:  # v1 뒤 Argon 1차 검토 자동 시작 (③ 의 일부). 락을 놓은 뒤에
                try:
                    await self.review(user, run_id)
                except (QueueFull, RunBusy, InvalidTransition) as exc:
                    logger.warning(
                        "run.auto_review_skipped run=%s reason=%s", run_id, type(exc).__name__
                    )
                    self._skip_review(user, run_id, state, "failed")
                    self._save(state)

    def _run_gate(self, gen: GenerateProposal) -> AbstractAsyncContextManager[None]:
        """run 전체가 잡는 슬롯 — 로컬 작성이면 전역 슬롯(1칸), Argon 작성이면 run_slot(N칸)."""
        if not gen.writes_remotely:
            return self.slot.acquire()
        if self.run_slot is not None:
            return self.run_slot.acquire()
        return contextlib.nullcontext()

    def _local_gate(self, gen: GenerateProposal) -> AbstractAsyncContextManager[None]:
        """run 안의 로컬 모델 단계 — Argon 작성일 때만 전역 슬롯을 잡는다
        (로컬 작성은 run 전체가 이미 잡고 있다)."""
        if gen.writes_remotely:
            return self.slot.acquire()
        return contextlib.nullcontext()

    async def _compose_sections(
        self,
        user: str,
        run_id: str,
        state: RunState,
        gen: GenerateProposal,
        req: ProposalRequest,
        snapshot: RetrievalSnapshot,
        outline: Outline | None,
        sections: dict[str, Section],
        on_step: StepCallback | None,
    ) -> None:
        """섹션 작성 — 로컬 작성은 순서대로 하나씩, Argon 작성은 compose_concurrency 개씩 동시에.
        섹션마다 검증을 통과한 뒤 저장한다(재개 단위). 하나가 실패하면 나머지를 취소하고
        그 예외를 올린다."""
        candidates = self.store.load_candidates(user, run_id) or {}
        want_b = self.pipeline.two_candidates and self.reviewer is not None
        pending: list[str] = []
        for key in self.generate.section_keys:
            if key in sections:
                self._ensure_done(state, section_step(key))
            else:
                pending.append(key)

        async def one(key: str) -> None:
            step = self._begin(state, section_step(key))
            try:
                composed = await gen.compose_section(key, req, snapshot, outline=outline)
                self.store.save_section(user, run_id, composed.section)
                if want_b and key in CORE_SECTIONS and composed.mode == "llm":
                    # Q7 후보 B — 같은 섹션을 다른 구성으로 한 번 더. 1차 검토가 고른다
                    alt = await gen.compose_section(
                        key, req, snapshot, outline=outline, candidate=composed.section
                    )
                    if alt.section.sentences:
                        candidates[key] = alt.section.model_dump(mode="json")
                        self.store.save_candidates(user, run_id, candidates)
            except BaseException as exc:
                step.status, step.error, step.finished_at = (
                    "error",
                    type(exc).__name__,
                    self._clock(),
                )
                raise
            self._record_section(run_id, state, step, key, composed, sections, on_step)

        limit = max(1, int(gen.compose_concurrency)) if gen.writes_remotely else 1
        if limit == 1 or len(pending) <= 1:
            for key in pending:
                await one(key)
            return
        sem = asyncio.Semaphore(limit)

        async def bounded(key: str) -> None:
            async with sem:
                await one(key)

        try:
            async with asyncio.TaskGroup() as group:
                for key in pending:
                    group.create_task(bounded(key))
        except ExceptionGroup as eg:  # 첫 실패를 그대로 (step 기록·manifest 는 클래스명만)
            raise eg.exceptions[0] from None

    def _record_section(
        self,
        run_id: str,
        state: RunState,
        step: StepRecord,
        key: str,
        composed: Any,
        sections: dict[str, Section],
        on_step: StepCallback | None,
    ) -> None:
        parse = composed.parse
        if parse is not None and parse.stripped:
            logger.warning(
                "run.tag_fragments_stripped run=%s section=%s n=%d",
                run_id,
                key,
                parse.stripped,
            )
        if parse is not None and not parse.ok:
            partial = parse.status == "choices_only"
            event = "parse_partial" if partial else "parse_failed"
            logger.warning(
                "run.%s run=%s section=%s reason=%s raw_chars=%d",
                event,
                run_id,
                key,
                parse.status,
                parse.raw_chars,
            )
        sections[key] = composed.section
        fb = getattr(composed, "fallback", None)
        if fb:  # 대체 작성(ADR 0027) — 전송 기록만 (본문 없음)
            state.fallback_sections = [
                x for x in state.fallback_sections if x.get("key") != key
            ] + [{"key": key, **fb}]
            logger.warning(
                "run.section_fallback run=%s section=%s reason=%s provider=%s",
                run_id,
                key,
                fb.get("reason"),
                fb.get("provider"),
            )
        writer = getattr(composed, "writer", None)
        if writer:  # 작성 기록(ADR 0032) — provider/model·로컬 대체·사유·전송 doc_id (본문 없음)
            state.writers[key] = dict(writer)
            if writer.get("local_fallback"):
                logger.warning(
                    "run.section_local_fallback run=%s section=%s reason=%s",
                    run_id,
                    key,
                    writer.get("reason"),
                )
        self._finish(
            state,
            step,
            on_step,
            sentences=len(composed.section.sentences),
            dropped=len(composed.dropped),
            evidence=sorted({e for s in composed.section.sentences for e in s.evidence}),
            prompt_hash=composed.prompt_hash,
            parse=parse.status if parse is not None else composed.mode,
            raw_chars=parse.raw_chars if parse is not None else None,
            retries=composed.retries,
            fallback=f"{fb['provider']}/{fb['model']}" if fb else None,
        )

    async def _live_step(self, user: str, state: RunState, req: ProposalRequest) -> None:
        """[4] 같은 입력의 실시간 검색 세션을 이어 쓰거나 시작하고 최대 wait_seconds 기다린다.
        못 끝나면 DB 만으로 계속(pending). 요약·실시간 doc_id 를 run 상태에 남긴다(본문 없음)."""
        if self.live_search is None or state.live_search is not None:
            return
        try:
            summary = await self.live_search.prepare(user, req)
        except Exception as exc:  # 실시간 검색 실패가 생성을 막지 않는다
            logger.warning("run.live_search_failed err=%s", type(exc).__name__)
            return
        if summary.status == "off":
            return
        state.live_search = summary.payload()
        state.live_doc_ids = list(summary.doc_ids)
        self._save(state)

    async def _outline_step(
        self,
        user: str,
        run_id: str,
        state: RunState,
        req: ProposalRequest,
        snapshot: RetrievalSnapshot,
        on_step: StepCallback | None,
    ) -> Outline | None:
        """Q2 섹션 설계도 — 저장된 것이 있으면 그대로(재개), 없으면 로컬 모델이 만든다. 실패하면
        단계를 error 로 적고 설계도 없이 계속한다 (생성을 막지 않는다)."""
        planned = any(s.name == OUTLINE for s in state.steps)
        if not (self.pipeline.outline and self.outliner is not None and planned):
            return None
        stored = self.store.load_outline(user, run_id)
        if stored is not None:
            self._ensure_done(state, OUTLINE)
            return Outline.model_validate(stored)
        step = self._begin(state, OUTLINE)
        outline = await self.outliner(req, snapshot)
        if outline is None:
            step.status, step.error, step.finished_at = "error", "OutlineFailed", self._clock()
            self._save(state)
            logger.warning("run.outline_failed run=%s", run_id)
            return None
        outline = outline.model_copy(update={"created_at": self._clock()})
        self.store.save_outline(user, run_id, outline.model_dump(mode="json"))
        self._finish(
            state,
            step,
            on_step,
            sentences=len(outline.sections),
            dropped=len(outline.discarded),
            retries=outline.retries,
        )
        return outline

    async def load_outline(self, user: str, run_id: str) -> dict[str, Any] | None:
        """③ 저장된 섹션 설계도(outline.json). 없으면 None."""
        await self.status(user, run_id)
        return self.store.load_outline(user, run_id)

    def _begin(self, state: RunState, name: str) -> StepRecord:
        step = state.step(name)
        step.status, step.error = "pending", None
        step.started_at, step.finished_at = self._clock(), None
        self._save(state)
        return step

    def _finish(
        self,
        state: RunState,
        step: StepRecord,
        on_step: StepCallback | None,
        **fields: Any,
    ) -> None:
        for name, value in fields.items():
            setattr(step, name, value)
        step.status, step.finished_at = "done", self._clock()
        self._save(state)
        if on_step is not None:
            on_step(state, step)

    def _ensure_done(self, state: RunState, name: str) -> None:
        step = state.step(name)
        if step.status != "done":  # 체크포인트는 있는데 상태 기록만 못 한 경우
            step.status, step.error = "done", None

    def _interrupt(self, state: RunState, step: StepRecord | None, error: str) -> None:
        state.status = "interrupted"
        if step is not None:
            step.status, step.error, step.finished_at = "error", error, self._clock()

    def _save(self, state: RunState) -> None:
        state.updated_at = self._clock()
        self.store.save_state(state)
        self._record(state)

    def _record(self, state: RunState) -> None:
        reviews = [
            r
            for n in self.store.list_reviews(state.user, state.run_id)
            if (r := self.store.load_review(state.user, state.run_id, n)) is not None
        ]
        versions = [
            v
            for n in self.store.list_versions(state.user, state.run_id)
            if (v := self.store.load_version(state.user, state.run_id, n)) is not None
        ]
        self.run_log.record(
            state.run_id,
            manifest(
                state,
                self.store.load_snapshot(state.user, state.run_id),
                self.store.load_confirmation(state.user, state.run_id),
                reviews,
                versions,
                self.store.load_usage(state.user, state.run_id),
            ),
        )

    # ── 조회 ─────────────────────────────────────────────
    async def status(self, user: str, run_id: str) -> RunState:
        if not is_valid_run_id(run_id):
            raise RunNotFound("run_id 형식이 올바르지 않습니다.")
        state = self.store.load_state(user, run_id)
        return self._normalize(state)

    def list_runs(self, user: str, limit: int = 50) -> list[RunState]:
        return [self._normalize(s) for s in self.store.list_runs(user, limit)]

    def list_all_runs(self, limit: int = 50) -> list[RunState]:
        """관리자용 — 모든 사용자의 run (최근 순). 소유자는 state.user."""
        out: list[RunState] = []
        for owner in self.store.list_users():
            out.extend(self.list_runs(owner, limit))
        out.sort(key=lambda s: s.run_id, reverse=True)
        return out[:limit]

    def find_owner(self, run_id: str) -> str | None:
        """관리자용 — run_id 의 소유자 키. 없으면 None."""
        for owner in self.store.list_users():
            try:
                self.store.load_state(owner, run_id)
            except (RunNotFound, ValueError):
                continue
            return owner
        return None

    def _generate_for(self, state: RunState) -> GenerateProposal:
        if state.scope == "public" and self.generate_public is not None:
            return self.generate_public
        return self.generate

    def _budget_exhausted(self) -> bool:
        return self.review_budget is not None and self.review_budget.exhausted()

    def _plan(self) -> list[str]:
        return plan_steps(
            self.generate.section_keys,
            outline=self.pipeline.outline,
            draft_review=self.pipeline.draft_review and self.first_pass,
            figures=self.figures is not None,
        )

    def _normalize(self, state: RunState) -> RunState:
        state.status = review_flow.normalize_status(state.status)  # 옛 이름(done·reviewed…)
        """queued·running 인데 아무도 락을 잡고 있지 않으면 실행하던 프로세스가 죽은 것."""
        if state.status in ACTIVE and not self.runner.is_running(state.run_id):
            if not self.store.is_alive(state.user, state.run_id):
                state.status = "interrupted"
                state.updated_at = self._clock()
                self.store.save_state(state)
                self._record(state)
        return state

    async def load_request(self, user: str, run_id: str) -> ProposalRequest:
        """저장된 제안 입력 — 예전 양식 run 의 입력으로 새 run 을 만들 때 쓴다.

        예전 request.json 은 새 모델로 그대로 읽힌다 (새 필드는 기본값, 없어진 필드는 무시).
        """
        await self.status(user, run_id)  # 형식·존재 확인
        return self.store.load_request(user, run_id)

    def is_legacy(self, state: RunState) -> bool:
        """현재 양식과 다른 run — 양식 id 또는 섹션 계획이 다르다."""
        return (
            state.template != self.generate.template
            or state.section_keys != self.generate.section_keys
        )

    async def get_draft(self, user: str, run_id: str) -> DraftView:
        state = await self.status(user, run_id)
        stored = self.store.load_sections(user, run_id)
        # 순서는 run 이 계획한 순서 — 양식이 바뀌어도 예전 run 은 자기 섹션으로 보인다.
        # 예전 run 에 남은 출처 조각((文档ID: …) 등)은 읽을 때 정리한다 — 화면·검토 입력 보호.
        sections = [_cleaned(stored[k]) for k in state.section_keys if k in stored]
        snapshot = self.store.load_snapshot(user, run_id)
        legacy = self.is_legacy(state)
        reviews = self.store.list_reviews(user, run_id)
        current = (
            self.store.load_version(user, run_id, state.draft_version)
            if state.draft_version
            else None
        )
        return DraftView(
            state=state,
            sections=sections,
            figures=list(current.figures) if current else [],
            citations=await self._citations(sections, snapshot),
            legacy=legacy,
            confirmation=self.store.load_confirmation(user, run_id),
            choice_options={} if legacy else self.generate.choice_options(),
            version=max(state.draft_version, 1),
            versions=self.store.list_versions(user, run_id),
            review=self.store.load_review(user, run_id, reviews[-1]) if reviews else None,
            reviews=reviews,
            has_working=self.store.load_working(user, run_id) is not None,
            strategy_status=self.generate.strategy.status,
        )

    # ── ③ Argon 1차 검토 → v2 / ⑤ 최종 검토 ─────────────────
    async def review(self, user: str, run_id: str) -> RunState:
        """③ 1차 검토(draft review)를 시작한다 — 초안 생성의 일부. 검토 LLM 이 없으면 건너뛰고
        draft_review_skipped 를 기록한다. 한 run 에 한 번(round 1). 백그라운드로 돈다."""
        state = await self.status(user, run_id)
        if self.is_legacy(state):
            raise InvalidTransition(LEGACY_HINT.format(run_id=run_id))
        if self.store.list_reviews(user, run_id) and self.store.load_review(user, run_id, 1):
            first = self.store.load_review(user, run_id, 1)
            if first is not None and first.status == "done":
                raise InvalidTransition("1차 검토는 한 번만 — 최종 검토는 final_review 로 요청.")
        if self.reviewer is None:
            if state.status not in ("drafted", "running", "editing"):
                raise InvalidTransition(review_flow.hint(state.status, "finish_draft_review"))
            self._skip_review(user, run_id, state, "no_review_llm")
            self._save(state)
            return state
        if self._budget_exhausted():  # 일일 상한 — 검토 없이 진행 (화면 알림은 flow 요약으로)
            if state.status not in ("drafted", "running", "editing"):
                raise InvalidTransition(review_flow.hint(state.status, "finish_draft_review"))
            self._skip_review(user, run_id, state, "budget")
            self._save(state)
            return state
        nxt = review_flow.start_draft_review(state.status)  # 불가면 InvalidTransition
        return await self._launch_review(user, run_id, state, nxt, kind="draft")

    async def final_review(self, user: str, run_id: str) -> RunState:
        """⑤ 최종 검토 — 제안자가 요청할 때 최신 저장 버전으로 1회. 임시 편집이 있으면 거부.
        최종 검토 뒤 다시 고치면 stale 표시만 하고, 다시 받기도 이 메서드(횟수 기록)."""
        state = await self.status(user, run_id)
        if self.is_legacy(state):
            raise InvalidTransition(LEGACY_HINT.format(run_id=run_id))
        if self.store.load_working(user, run_id) is not None:
            raise InvalidTransition(
                "저장하지 않은 임시 편집이 있습니다 — 먼저 저장하거나 버리십시오."
            )
        if self.reviewer is None:
            raise InvalidTransition(
                "검토 LLM 이 없습니다 (review_skipped) — 바로 마무리할 수 있습니다."
            )
        if self._budget_exhausted():
            review_flow.transition(state.status, "start_final_review")  # 상태 검사만
            state.review_skipped = True  # 검토 없이 마무리할 수 있게
            state.review_error = "BudgetExhausted"
            self._save(state)
            raise ReviewBudgetExhausted(
                "외부 검토 LLM 의 오늘 호출 상한을 넘어 검토 없이 진행합니다 — "
                "바로 마무리할 수 있습니다."
            )
        nxt = review_flow.transition(state.status, "start_final_review")
        return await self._launch_review(user, run_id, state, nxt, kind="final")

    async def _launch_review(
        self, user: str, run_id: str, state: RunState, nxt: str, *, kind: str
    ) -> RunState:
        active = [s for s in self.list_runs(user) if s.status in ACTIVE and s.run_id != run_id]
        if len(active) >= self.max_queued:
            raise QueueFull(
                f"대기·실행 중인 작업이 {len(active)}건입니다 (상한 {self.max_queued})."
            )
        claim = self.store.claim(user, run_id)
        state.review_from = state.status
        state.status = nxt
        state.review_error = None
        self._save(state)
        key = _review_key(run_id, len(self.store.list_reviews(user, run_id)) + 1)
        self._review_tasks[run_id] = key
        self.runner.submit(key, self._execute_review(user, run_id, claim, kind=kind))
        return state

    def _skip_review(self, user: str, run_id: str, state: RunState, reason: str) -> None:
        """1차 검토를 돌리지 않음 — v1 로 진행.
        reason: no_review_llm | budget | disabled | failed."""
        if reason in ("no_review_llm", "budget"):  # 검토를 할 수 없을 때는 ⑤ 없이 ⑥ 으로
            state.review_skipped = True
        state.draft_review_skipped = reason
        try:
            step = state.step(DRAFT_REVIEW)
            step.status, step.error = (
                ("skipped", None) if reason != "failed" else ("error", "failed")
            )
            step.finished_at = self._clock()
        except KeyError:
            pass
        if not self.store.list_reviews(user, run_id):
            self.store.save_review(
                user,
                run_id,
                ReviewRound(
                    round=1,
                    kind="draft",
                    draft_version=max(state.draft_version, 1),
                    status="skipped",
                    skipped_reason=reason,
                    created_at=self._clock(),
                ),
            )

    async def _execute_review(
        self, user: str, run_id: str, claim: RunClaim, *, kind: str = "draft"
    ) -> RunState:
        state = self.store.load_state(user, run_id)
        reviewer = self.reviewer
        if reviewer is None:  # review() 가 막지만 방어
            raise RuntimeError("reviewer missing")
        attempts = 1 + (self.pipeline.draft_review_retries if kind == "draft" else 0)
        step = None
        try:
            # 검토는 Argon 만 쓴다 — Argon 작성이면 run_slot(N칸), 로컬 작성이면 예전대로 전역 슬롯
            async with self._run_gate(self.generate):
                if kind == "draft":
                    try:
                        step = self._begin(state, DRAFT_REVIEW)
                    except KeyError:
                        step = None
                version = self._current_version(user, run_id, state)
                snapshot = self.store.load_snapshot(user, run_id)
                if snapshot is None:
                    raise RuntimeError("retrieval snapshot missing")
                rounds = self.store.list_reviews(user, run_id)
                draft_round = self.store.load_review(user, run_id, 1) if rounds else None
                previous = draft_round if draft_round and draft_round.status == "done" else None
                changed = self._changed_since(user, run_id, version, previous)
                round_no = len(rounds) + 1 if kind == "final" else 1
                if kind == "final" and round_no < 2:
                    round_no = 2  # 1차가 건너뛰어졌어도 최종 검토는 round 2 부터
                candidates: dict[str, Section] = {}
                if kind == "draft" and self.pipeline.two_candidates:
                    candidates = {
                        k: Section.model_validate(v)
                        for k, v in (self.store.load_candidates(user, run_id) or {}).items()
                    }
                ctx = ReviewContext(
                    run_id=run_id,
                    round_no=round_no,
                    version=version,
                    snapshot=snapshot,
                    request=self.store.load_request(user, run_id),
                    previous=previous if kind == "final" else None,
                    changed=changed if kind == "final" else frozenset(),
                    confirmation=self.store.load_confirmation(user, run_id),
                    kind=kind,
                    app_findings=tuple(
                        f"{p['section']}: {p.get('message', p['code'])}"
                        for p in state.problems
                        if p.get("severity") == "warning"
                    )
                    if kind == "draft"
                    else (),
                    candidates=candidates,
                    figures=[f for f in version.figures if f.included],
                )
                last_exc: Exception | None = None
                result = None
                for _ in range(attempts):
                    try:
                        result = await reviewer(ctx)
                        break
                    except (
                        Exception
                    ) as exc:  # 1차 검토는 재시도 1회 (pipeline.draft_review_retries)
                        last_exc = exc
                if result is None:
                    raise last_exc or RuntimeError("review failed")
                result = result.model_copy(
                    update={"created_at": self._clock(), "kind": kind, "round": round_no}
                )
                state.review_model = (
                    f"{reviewer.provider}/{reviewer.model}"
                    if reviewer.provider or reviewer.model
                    else None
                )
                if kind == "draft":
                    result = self._apply_draft_review(user, run_id, state, version, result)
                    self.store.save_review(user, run_id, result)
                    if result.support:  # U1 불일치 판정 → 문장 경고
                        self._refresh_problems(user, run_id, state)
                    self._touch_usage(
                        user,
                        run_id,
                        state,
                        checklist_coverage=getattr(result, "checklist_coverage", None),
                    )
                    state.review_rounds += 1
                    state.draft_review_skipped = None
                    state.status = review_flow.transition(state.status, "finish_draft_review")
                    if step is not None:
                        self._finish(
                            state,
                            step,
                            None,
                            sentences=len(result.applied_ids),
                            dropped=sum(1 for c in result.comments if c.status == "discarded"),
                        )
                else:
                    if previous is not None and previous.scores:
                        before = {x.criterion: x.score for x in previous.scores}
                        result = result.model_copy(
                            update={
                                "score_delta": {
                                    x.criterion: x.score - before[x.criterion]
                                    for x in result.scores
                                    if x.criterion in before
                                }
                            }
                        )
                    self.store.save_review(user, run_id, result)
                    self._mark_resolved(user, run_id, previous, result.resolved_ids)
                    state.review_rounds += 1
                    state.final_reviews += 1
                    state.final_reviewed_version = version.version
                    state.stale_edits = 0
                    state.status = review_flow.transition(state.status, "finish_final_review")
                state.review_from = None
                return state
        except Exception as exc:  # 검토 실패 — 검토 전 상태로 (초안은 그대로)
            over_budget = isinstance(exc, BudgetExhausted)
            if kind == "draft":
                state.status = review_flow.transition("draft_reviewing", "fail_draft_review")
                self._skip_review(user, run_id, state, "budget" if over_budget else "failed")
            else:
                state.status = review_flow.transition(
                    "final_reviewing", "fail_final_review", previous=state.review_from
                )
                if over_budget:
                    state.review_skipped = True
            state.review_error = type(exc).__name__
            state.review_from = None
            logger.warning(
                "run.review_failed run=%s kind=%s error=%s", run_id, kind, type(exc).__name__
            )
            return state
        finally:
            self._save(state)
            claim.release()

    def _apply_draft_review(
        self, user: str, run_id: str, state: RunState, v1: DraftVersion, review: ReviewRound
    ) -> ReviewRound:
        """③ 검증을 통과한 수정안·추가 문장만 자동 반영 → v2(origin=argon). 폐기된 수정안과 수정안
        없는 의견은 문장 메모(annotations)로 v2 에 붙인다. 선택형 섹션의 선택값은 바꾸지 않는다."""
        by_key = {sec.key: sec for sec in v1.sections}
        applied: list[str] = []
        # Q7 후보 선택 — B 를 고른 섹션은 통째로 바꾸고, A 문장 기준 의견은 더 쓰지 않는다
        review, replaced = self._choose_candidates(user, run_id, review, by_key)
        for c in review.comments:
            if c.kind != "revision" or not (c.usable and c.sentence is not None):
                continue
            if c.section in replaced:
                continue
            sec = by_key.get(c.section)
            if sec is None or c.sentence >= len(sec.sentences):
                continue
            original = sec.sentences[c.sentence]
            if original.origin == "app":
                continue  # 앱 확정 문장은 손대지 않는다
            sentences = list(sec.sentences)
            sentences[c.sentence] = Sentence(
                text=c.revised_text or original.text,
                evidence=list(c.evidence or original.evidence),
                origin="argon",
            )
            by_key[c.section] = sec.model_copy(update={"sentences": sentences})
            applied.append(c.id)
        # Q5 추가 문장 — 검증 통과분만, 섹션 뒤쪽부터 끼워 넣어 인덱스가 밀리지 않게
        additions = [
            c
            for c in review.comments
            if c.kind == "addition"
            and c.usable
            and c.section in by_key
            and c.section not in replaced
        ]
        for c in sorted(additions, key=lambda c: -1 if c.after is None else -c.after):
            sec = by_key[c.section]
            sentences = list(sec.sentences)
            at = len(sentences) if c.after is None else min(c.after + 1, len(sentences))
            sentences.insert(
                at,
                Sentence(
                    text=c.revised_text or "", evidence=list(c.evidence), origin="argon_addition"
                ),
            )
            by_key[c.section] = sec.model_copy(update={"sentences": sentences})
            applied.append(c.id)
        sections = [by_key[sec.key] for sec in v1.sections]  # choices 는 그대로
        annotations = _annotations_from(review, applied)
        if not applied and not replaced:
            # 반영할 것이 없으면 v2 를 만들지 않고 메모만 v1 에 붙인다
            v1b = v1.model_copy(update={"annotations": annotations})
            self.store.save_version(user, run_id, v1b)
            return review.model_copy(
                update={
                    "applied_ids": [],
                    "applied_version": None,
                    "comments": [
                        c.model_copy(update={"status": "resolved"}) if c.id in applied else c
                        for c in review.comments
                    ],
                }
            )
        v2 = DraftVersion(
            version=v1.version + 1,
            origin="argon",
            sections=sections,
            created_at=self._clock(),
            based_on_review=review.round,
            note="Argon 1차 검토 반영",
            changed_sections=changed_sections(v1.sections, sections),
            annotations=annotations,
            figures=list(v1.figures),
        )
        self._store_version(user, run_id, state, v2, state.status)
        return review.model_copy(
            update={
                "applied_ids": applied,
                "applied_version": v2.version,
                "comments": [
                    c.model_copy(update={"status": "resolved"}) if c.id in applied else c
                    for c in review.comments
                ],
            }
        )

    def _choose_candidates(
        self, user: str, run_id: str, review: ReviewRound, by_key: dict[str, Section]
    ) -> tuple[ReviewRound, set[str]]:
        """Q7 — 검토가 고른 후보를 반영한다. 고르지 않았으면 A(초안) 유지. 버린 후보의 문장은
        review_draft.json(candidate_choices.rejected_text)에 남긴다."""
        stored = self.store.load_candidates(user, run_id) or {}
        if not stored:
            return review, set()
        choices = {k: dict(v) for k, v in review.candidate_choices.items()}
        replaced: set[str] = set()
        for key, raw in stored.items():
            if key not in by_key:
                continue
            alt = Section.model_validate(raw)
            pick = choices.get(key) or {"choice": "A", "reason": "검토가 고르지 않음 — A 유지"}
            if pick.get("choice") == "B" and alt.sentences:
                rejected = by_key[key]
                by_key[key] = alt.model_copy(update={"choices": rejected.choices})
                replaced.add(key)
                pick["rejected"] = "A"
                pick["rejected_text"] = rejected.text[:4000]
            else:
                pick["choice"] = "A"
                pick["rejected"] = "B"
                pick["rejected_text"] = alt.text[:4000]
            choices[key] = pick
        comments = [
            c.model_copy(update={"status": "discarded", "discard_reason": "candidate_replaced"})
            if c.section in replaced
            and c.status == "open"
            and (c.sentence is not None or c.kind == "addition")
            else c
            for c in review.comments
        ]
        return review.model_copy(update={"candidate_choices": choices, "comments": comments}), (
            replaced
        )

    def _current_version(self, user: str, run_id: str, state: RunState) -> DraftVersion:
        n = state.draft_version
        found = self.store.load_version(user, run_id, n) if n >= 1 else None
        if found is not None:
            return found
        stored = self.store.load_sections(user, run_id)  # 버전 파일이 없는 예전 run → v1 로 만든다
        sections = [_cleaned(stored[k]) for k in state.section_keys if k in stored]
        version = DraftVersion(
            version=1, origin="local", sections=sections, created_at=self._clock()
        )
        self.store.save_version(user, run_id, version)
        state.draft_version = 1
        return version

    def _changed_since(
        self, user: str, run_id: str, version: DraftVersion, previous: ReviewRound | None
    ) -> frozenset[str]:
        if previous is None:
            return frozenset()
        base = previous.applied_version or previous.draft_version
        old = self.store.load_version(user, run_id, base)
        if old is None:
            return frozenset()
        return frozenset(changed_sentence_ids(old, version))

    def _mark_resolved(
        self, user: str, run_id: str, previous: ReviewRound | None, resolved: list[str]
    ) -> None:
        if previous is None or not resolved:
            return
        updated = previous.model_copy(
            update={
                "comments": [
                    c.model_copy(update={"status": "resolved"}) if c.id in resolved else c
                    for c in previous.comments
                ]
            }
        )
        self.store.save_review(user, run_id, updated)

    # ── ④ 버전·편집·임시 저장·복원·비교 ───────────────────────
    async def versions(self, user: str, run_id: str) -> list[DraftVersion]:
        state = await self.status(user, run_id)
        self._current_version(user, run_id, state)
        out = []
        for n in self.store.list_versions(user, run_id):
            v = self.store.load_version(user, run_id, n)
            if v is not None:
                out.append(v)
        return out

    async def get_review(
        self, user: str, run_id: str, round_no: int | None = None, *, kind: str | None = None
    ) -> ReviewRound | None:
        """검토 결과 — round_no 가 없으면 최신 차수(kind 를 주면 그 종류의 최신). 없으면 None.
        kind="final" 일 때 round_no 는 최종 검토 차수(1..)이다."""
        await self.status(user, run_id)
        rounds = self.store.list_reviews(user, run_id)
        if not rounds:
            return None
        if kind == "draft":
            return self.store.load_review(user, run_id, 1) if 1 in rounds else None
        if kind == "final":
            finals = [n for n in rounds if n >= 2]
            if not finals:
                return None
            target = finals[-1] if round_no is None else round_no + 1
            return self.store.load_review(user, run_id, target) if target in finals else None
        if round_no is None:
            round_no = rounds[-1]
        return self.store.load_review(user, run_id, round_no) if round_no >= 1 else None

    async def get_version(self, user: str, run_id: str, version: int) -> DraftVersion:
        await self.status(user, run_id)
        found = self.store.load_version(user, run_id, version) if version >= 1 else None
        if found is None:
            raise EditRejected(f"버전 v{version} 이 없습니다.")
        return found

    async def diff(self, user: str, run_id: str, a: int, b: int) -> list[dict]:
        """두 버전의 섹션·문장 단위 차이."""
        return diff_versions(
            await self.get_version(user, run_id, a), await self.get_version(user, run_id, b)
        )

    async def save_working(self, user: str, run_id: str, data: dict[str, Any]) -> None:
        """④ 임시 저장(autosave) — 서버 작업 사본. 편집 가능한 상태에서만."""
        state = await self.status(user, run_id)
        if not review_flow.can_edit(state.status):
            raise WorkingRejected(review_flow.hint(state.status, "edit"))
        self.store.save_working(user, run_id, {**data, "saved_at": self._clock()})

    async def load_working(self, user: str, run_id: str) -> dict[str, Any] | None:
        await self.status(user, run_id)
        return self.store.load_working(user, run_id)

    async def discard_working(self, user: str, run_id: str) -> None:
        await self.status(user, run_id)
        self.store.clear_working(user, run_id)

    async def apply_edits(self, user: str, run_id: str, edits: EditRequest) -> DraftVersion:
        """④ 저장 — 편집을 반영한 새 버전 vN. 같은 내용이면 새 버전을 만들지 않는다.

        수정안 사용은 검증 통과분만, 직접 수정은 proposer_edit(근거 유지), 새 문장은 proposer_input.
        lint 는 알림만. base_version 이 현재와 다르면 VersionConflict(409). 저장 뒤 임시 사본 삭제.
        최종 검토 이후의 저장은 stale_edits 를 올린다.
        """
        state = await self.status(user, run_id)
        if self.is_legacy(state):
            raise EditRejected(LEGACY_HINT.format(run_id=run_id))
        try:
            nxt = review_flow.transition(state.status, "edit")
        except InvalidTransition as exc:
            raise EditRejected(str(exc)) from exc
        if not edits.sentences and not edits.sections and not edits.done_annotations:
            raise EditRejected("반영할 편집이 없습니다.")
        current = self._current_version(user, run_id, state)
        if edits.base_version is not None and edits.base_version != current.version:
            raise VersionConflict(
                f"기준 버전 v{edits.base_version} 과 현재 버전 v{current.version} 이 다릅니다 — "
                "최신 버전을 불러와 다시 저장하십시오."
            )
        rounds = self.store.list_reviews(user, run_id)
        latest = self.store.load_review(user, run_id, rounds[-1]) if rounds else None
        sections, used = apply_edit_request(current.sections, edits, latest)
        annotations = [
            a.model_copy(update={"status": "done"}) if a.id in set(edits.done_annotations) else a
            for a in current.annotations
        ]
        if same_content(current.sections, sections) and annotations == current.annotations:
            self.store.clear_working(user, run_id)
            return current  # 같은 내용 — 새 버전 없음
        origin = (
            "final_review" if (used and latest is not None and latest.kind == "final") else "edit"
        )
        new_version = DraftVersion(
            version=current.version + 1,
            origin=origin,
            sections=sections,
            created_at=self._clock(),
            based_on_review=latest.round if latest and used else None,
            note=edits.note,
            changed_sections=changed_sections(current.sections, sections),
            annotations=annotations,
            evidence_decisions=decisions_for_sections(sections, current.evidence_decisions),
            figures=list(current.figures),
        )
        self._store_version(user, run_id, state, new_version, nxt)
        if latest is not None and used:
            self.store.save_review(
                user,
                run_id,
                latest.model_copy(
                    update={
                        "comments": [
                            c.model_copy(update={"status": "resolved"}) if c.id in used else c
                            for c in latest.comments
                        ]
                    }
                ),
            )
        return self.store.load_version(user, run_id, new_version.version) or new_version

    async def revert(self, user: str, run_id: str, to: int) -> DraftVersion:
        """복원 — 이전 버전 내용으로 새 버전을 만든다 (기록은 지우지 않는다)."""
        state = await self.status(user, run_id)
        try:
            nxt = review_flow.transition(state.status, "edit")
        except InvalidTransition as exc:
            raise EditRejected(str(exc)) from exc
        current = self._current_version(user, run_id, state)
        target = self.store.load_version(user, run_id, to) if to >= 1 else None
        if target is None:
            raise EditRejected(f"버전 v{to} 이 없습니다.")
        new_version = DraftVersion(
            version=current.version + 1,
            origin="revert",
            sections=target.sections,
            created_at=self._clock(),
            reverted_from=to,
            note=f"v{to} 로 복원",
            changed_sections=changed_sections(current.sections, target.sections),
            annotations=target.annotations,
            evidence_decisions=decisions_for_sections(target.sections, target.evidence_decisions),
            figures=list(target.figures),  # 그림도 그 버전의 것으로 (파일은 해시로 남아 있다)
        )
        self._store_version(user, run_id, state, new_version, nxt)
        return self.store.load_version(user, run_id, new_version.version) or new_version

    def _store_version(
        self, user: str, run_id: str, state: RunState, version: DraftVersion, status: str
    ) -> None:
        previous = (
            self.store.load_version(user, run_id, state.draft_version)
            if state.draft_version
            else None
        )
        for section in version.sections:
            self.store.save_section(user, run_id, section)
        req = self.store.load_request(user, run_id)
        snapshot = self.store.load_snapshot(user, run_id)
        draft = Draft(
            run_id=run_id,
            request=req,
            sections=version.sections,
            retrieved_ids=snapshot.retrieved_ids if snapshot else set(),
            template=state.template,
        )
        problems = self._problems_for(user, run_id, draft, snapshot, version, state)
        version = version.model_copy(update={"alerts": len(problems)})
        self.store.save_version(user, run_id, version)
        state.failed_sections = draft_failures.still_failed(state.failed_sections, version.sections)
        problems = draft_failures.relax_failed(problems, state.failed_sections)
        state.problems = [
            p.model_dump() for p in problems
        ]  # 알림만 — 상태를 invalid 로 바꾸지 않는다
        state.draft_version = version.version
        state.figures = _figure_summary(version.figures, state.figures)
        if state.final_reviewed_version is not None and version.origin != "argon":
            base = self.store.load_version(user, run_id, state.final_reviewed_version)
            if base is not None:
                state.stale_edits = count_changed_sentences(base.sections, version.sections)
        state.status = status
        self.store.clear_working(user, run_id)
        self._touch_usage(
            user,
            run_id,
            state,
            counts=evidence_counts(version.sections, version.evidence_decisions),
        )
        self._save(state)
        del previous

    def _problems_for(
        self,
        user: str,
        run_id: str,
        draft: Draft,
        snapshot: RetrievalSnapshot | None,
        version: DraftVersion,
        state: RunState | None = None,
    ) -> list:
        """규칙 검사 전부 — lint·U6 일정 + U1 검토 판정 불일치·근거 전부 제외 경고 + local_check
        불일치(ADR 0032)."""
        problems = self.generate.lint_draft(draft, snapshot)
        if state is not None and state.local_check:
            problems.extend(local_check_problems(draft.sections, state.local_check))
        review = self.store.load_review(user, run_id, 1)
        if review is not None and review.support:
            problems.extend(support_problems(draft.sections, review.support))
        problems.extend(
            exclusion_problems(
                draft.sections, version.evidence_decisions, self.generate.rules.evidence_required
            )
        )
        return problems

    def _refresh_problems(self, user: str, run_id: str, state: RunState) -> None:
        version = self._current_version(user, run_id, state)
        snapshot = self.store.load_snapshot(user, run_id)
        draft = Draft(
            run_id=run_id,
            request=self.store.load_request(user, run_id),
            sections=version.sections,
            retrieved_ids=snapshot.retrieved_ids if snapshot else set(),
            template=state.template,
        )
        problems = self._problems_for(user, run_id, draft, snapshot, version, state)
        state.failed_sections = draft_failures.still_failed(state.failed_sections, version.sections)
        problems = draft_failures.relax_failed(problems, state.failed_sections)
        state.problems = [p.model_dump() for p in problems]
        self.store.save_version(user, run_id, version.model_copy(update={"alerts": len(problems)}))

    def _prioritize(self, user: str, run_id: str, snapshot: RetrievalSnapshot) -> RetrievalSnapshot:
        """U5 우선 근거 — 검색 집합 안의 id 만 남기고 그 청크를 앞으로."""
        notes = self.store.load_notes(user, run_id) or {}
        wanted = [str(x) for x in notes.get("priority_evidence") or []]
        if not wanted:
            return snapshot
        allowed = snapshot.retrieved_ids
        ids = [x for x in wanted if x in allowed]
        if not ids:
            return snapshot
        keys = set(ids)
        first = [c for c in snapshot.chunks if c.chunk_id in keys or c.doc_id in keys]
        rest = [c for c in snapshot.chunks if c not in first]
        snapshot.chunks = first + rest
        snapshot.priority_ids = ids
        return snapshot

    # ── U1 근거 원문 바로보기·제안자 판단 ──────────────────────
    async def sentence_evidence(self, user: str, run_id: str, sid: str) -> list[EvidenceItem]:
        """문장 id("s:<섹션>:<번호>")의 근거마다 원문 발췌·문서 메타·적합성·판단. 없는 문장은
        EditRejected."""
        if not self.usability.evidence_view:
            raise FeatureDisabled("근거 원문 보기가 꺼져 있습니다 (usability.yaml evidence_view).")
        state = await self.status(user, run_id)
        version = self._current_version(user, run_id, state)
        parsed = parse_sentence_id(sid)
        if parsed is None:
            raise EditRejected(f"문장 id 형식이 올바르지 않습니다: {sid}")
        key, idx = parsed
        sec = version.section(key)
        if sec is None or idx >= len(sec.sentences):
            raise EditRejected(f"그런 문장이 없습니다: {sid}")
        sentence = sec.sentences[idx]
        snapshot = self.store.load_snapshot(user, run_id)
        chunks = {c.chunk_id: c for c in (snapshot.chunks if snapshot else [])}
        by_doc: dict[str, list] = {}
        for c in chunks.values():
            by_doc.setdefault(c.doc_id, []).append(c)
        review = self.store.load_review(user, run_id, 1)
        support = review.support.get(sid) if review and review.support else None
        decided = {
            d.evidence_id: d.action for d in version.evidence_decisions if d.sentence_id == sid
        }
        allowed = snapshot.retrieved_ids if snapshot else set()
        out: list[EvidenceItem] = []
        for ev in sentence.evidence:
            chunk = chunks.get(ev)
            doc_id = chunk.doc_id if chunk else ev.split("#", 1)[0]
            if chunk is None and by_doc.get(doc_id):
                chunk = by_doc[doc_id][0]
            doc = await self.generate.repo.get_document(doc_id)
            basis = chunk.basis if chunk and chunk.basis else (doc.text_basis if doc else None)
            raw = dict(doc.raw) if doc else {}
            ingested = raw.get("ingested_at")
            out.append(
                EvidenceItem(
                    evidence_id=ev,
                    doc_id=doc_id,
                    chunk_id=chunk.chunk_id if chunk else None,
                    text=excerpt(
                        chunk.text if chunk else ((doc.abstract or doc.body or "") if doc else "")
                    ),
                    title=doc.title if doc else None,
                    source=doc.source if doc else doc_id.split(":", 1)[0],
                    source_label=SOURCE_LABELS.get(
                        doc.source if doc else doc_id.split(":", 1)[0], doc_id.split(":", 1)[0]
                    ),
                    orgs=list(doc.orgs) if doc else [],
                    year=doc.pub_date.year if doc and doc.pub_date else None,
                    ingested_at=str(ingested) if ingested else None,
                    basis=basis,
                    basis_label=basis_label(basis),
                    needs_check=needs_check(basis),
                    support=support,
                    decision=decided.get(ev),
                    in_snapshot=ev in allowed or doc_id in allowed,
                    url=_evidence_url(doc, raw, basis),
                )
            )
        return out

    async def decide_evidence(
        self, user: str, run_id: str, request: EvidenceDecisionRequest
    ) -> DraftVersion:
        """U1 제안자 근거 판단 → 새 버전(origin=edit, note 기본 "근거 판단"). replace 는 검색 집합
        안의 id 로만. 같은 판단이면 새 버전 없음."""
        if not self.usability.evidence_decisions:
            raise FeatureDisabled(
                "근거 판단 저장이 꺼져 있습니다 (usability.yaml evidence_decisions)."
            )
        state = await self.status(user, run_id)
        if self.is_legacy(state):
            raise EditRejected(LEGACY_HINT.format(run_id=run_id))
        try:
            nxt = review_flow.transition(state.status, "edit")
        except InvalidTransition as exc:
            raise EditRejected(str(exc)) from exc
        if not request.decisions:
            raise EditRejected("반영할 판단이 없습니다.")
        current = self._current_version(user, run_id, state)
        if request.base_version is not None and request.base_version != current.version:
            raise VersionConflict(
                f"기준 버전 v{request.base_version} 과 현재 버전 v{current.version} 이 다릅니다 — "
                "최신 버전을 불러와 다시 저장하십시오."
            )
        snapshot = self.store.load_snapshot(user, run_id)
        allowed = snapshot.retrieved_ids if snapshot else set()
        try:
            sections, decisions = apply_decisions(
                current.sections, current.evidence_decisions, request.decisions, allowed
            )
        except DecisionRejected as exc:
            raise EditRejected(str(exc)) from exc
        same = same_content(current.sections, sections) and sorted(
            d.model_dump() for d in decisions
        ) == sorted(d.model_dump() for d in current.evidence_decisions)
        if same:
            return current
        new_version = DraftVersion(
            version=current.version + 1,
            origin="edit",
            sections=sections,
            created_at=self._clock(),
            note=request.note or "근거 판단",
            changed_sections=changed_sections(current.sections, sections),
            annotations=current.annotations,
            evidence_decisions=decisions,
            figures=list(current.figures),  # 근거 판단으로 그림이 빠지지 않게
        )
        self._store_version(user, run_id, state, new_version, nxt)
        return self.store.load_version(user, run_id, new_version.version) or new_version

    # ── U3 섹션별 AI 다시 쓰기·보완 질문 ────────────────────────
    async def rewrite_section(self, user: str, run_id: str, key: str) -> RewriteView:
        """섹션 하나를 로컬 모델로 다시 쓴 후보 (반영 전). 제안자 수정 문장은 보존, 선택값 불변.
        후보는 rewrites/rewrite_<key>.json 에 두고 apply_rewrite 로 반영한다."""
        if not self.usability.section_rewrite:
            raise FeatureDisabled(
                "섹션 다시 쓰기가 꺼져 있습니다 (usability.yaml section_rewrite)."
            )
        state = await self.status(user, run_id)
        if self.is_legacy(state):
            raise RewriteRejected(LEGACY_HINT.format(run_id=run_id))
        if not review_flow.can_edit(state.status):
            raise RewriteRejected(review_flow.hint(state.status, "edit"))
        if key not in self.generate.section_keys:
            raise RewriteRejected(f"그런 섹션이 없습니다: {key}")
        version = self._current_version(user, run_id, state)
        current = version.section(key) or Section(key=key, sentences=[])
        snapshot = self.store.load_snapshot(user, run_id)
        if snapshot is None:
            raise RewriteRejected("검색 스냅샷이 없어 다시 쓸 수 없습니다.")
        notes = (self.store.load_notes(user, run_id) or {}).get("answers", {}).get(key) or {}
        # 로컬 작성: 전역 슬롯 안에서. Argon 작성: 로컬 대체가 필요할 때만 유스케이스가
        # 슬롯을 잡는다
        gen = self._generate_for(state)  # 공용 계정 run 은 internal 제외 유스케이스
        gate = self.slot.acquire() if not gen.writes_remotely else contextlib.nullcontext()
        async with gate:
            try:
                composed = await gen.rewrite_section(
                    key, self.store.load_request(user, run_id), snapshot, current, notes=notes
                )
            except ValueError as exc:
                raise RewriteRejected(str(exc)) from exc
        candidate = _cleaned(composed.section)
        now = self._clock()
        self.store.save_rewrite(
            user,
            run_id,
            key,
            {
                "section": key,
                "base_version": version.version,
                "candidate": candidate.model_dump(mode="json"),
                "dropped": len(composed.dropped),
                "created_at": now,
            },
        )
        return RewriteView(
            section=key,
            current=current,
            candidate=candidate,
            rows=side_by_side(current, candidate),
            dropped=list(composed.dropped),
            created_at=now,
        )

    async def apply_rewrite(
        self,
        user: str,
        run_id: str,
        key: str,
        *,
        chosen: list[int] | None = None,
        base_version: int | None = None,
        note: str = "",
    ) -> DraftVersion:
        """다시 쓰기 후보를 반영 → 새 버전(origin=edit, note "AI 다시 쓰기"). chosen 은 후보 문장
        인덱스(없으면 전부). 후보가 만들어진 버전과 현재 버전이 다르면 VersionConflict."""
        state = await self.status(user, run_id)
        try:
            nxt = review_flow.transition(state.status, "edit")
        except InvalidTransition as exc:
            raise RewriteRejected(str(exc)) from exc
        stored = self.store.load_rewrite(user, run_id, key)
        if not stored:
            raise RewriteRejected(
                f"{key}: 반영할 다시 쓰기 후보가 없습니다 — 먼저 rewrite 를 요청."
            )
        current = self._current_version(user, run_id, state)
        base = base_version if base_version is not None else stored.get("base_version")
        if base is not None and base != current.version:
            raise VersionConflict(
                f"후보 기준 버전 v{base} 과 현재 버전 v{current.version} 이 다릅니다 — 다시 요청."
            )
        candidate = Section.model_validate(stored["candidate"])
        if chosen is not None and any(i < 0 or i >= len(candidate.sentences) for i in chosen):
            raise RewriteRejected("후보에 없는 문장 번호입니다.")
        picked = pick(candidate, chosen)
        sections = [picked if s.key == key else s for s in current.sections]
        if same_content(current.sections, sections):
            self.store.clear_rewrite(user, run_id, key)
            return current
        new_version = DraftVersion(
            version=current.version + 1,
            origin="edit",
            sections=sections,
            created_at=self._clock(),
            note=note or REWRITE_NOTE,
            changed_sections=changed_sections(current.sections, sections),
            annotations=current.annotations,
            evidence_decisions=decisions_for_sections(sections, current.evidence_decisions),
            figures=list(current.figures),  # 다시 쓰기로 그림이 빠지지 않게
        )
        self._store_version(user, run_id, state, new_version, nxt)
        self.store.clear_rewrite(user, run_id, key)
        self._touch_usage(user, run_id, state, rewrites_add=1)
        return self.store.load_version(user, run_id, new_version.version) or new_version

    async def section_questions(self, user: str, run_id: str, key: str) -> dict[str, Any]:
        """섹션 체크리스트에서 빠진 요소 → 보완 질문. 답(proposer_notes.json)이 있으면 함께."""
        if not self.usability.section_questions:
            raise FeatureDisabled("보완 질문이 꺼져 있습니다 (usability.yaml section_questions).")
        state = await self.status(user, run_id)
        if key not in state.section_keys:
            raise EditRejected(f"그런 섹션이 없습니다: {key}")
        version = self._current_version(user, run_id, state)
        checklist = self.checklists.get(key, [])
        answers = (self.store.load_notes(user, run_id) or {}).get("answers", {}).get(key) or {}
        return {
            "section": key,
            "questions": missing_elements(version.section(key), checklist),
            "coverage": coverage(version.section(key), checklist),
            "answers": dict(answers),
        }

    async def save_section_answers(
        self, user: str, run_id: str, key: str, answers: Mapping[str, Any]
    ) -> dict[str, str]:
        """보완 질문의 답을 제안자 입력으로 저장 (proposer_notes.json) — 다음 다시 쓰기에."""
        state = await self.status(user, run_id)
        if key not in state.section_keys:
            raise EditRejected(f"그런 섹션이 없습니다: {key}")
        cleaned = clean_answers(answers)
        notes = self.store.load_notes(user, run_id) or {}
        all_answers = dict(notes.get("answers") or {})
        merged = {**(all_answers.get(key) or {}), **cleaned}
        all_answers[key] = merged
        self.store.save_notes(
            user, run_id, {**notes, "answers": all_answers, "saved_at": self._clock()}
        )
        return merged

    # ── U7 제출 전 점검 ─────────────────────────────────
    async def submit_check(self, user: str, run_id: str) -> SubmitCheck:
        if not self.usability.submit_check:
            raise FeatureDisabled("제출 전 점검이 꺼져 있습니다 (usability.yaml submit_check).")
        state = await self.status(user, run_id)
        version = self._current_version(user, run_id, state) if state.status in FINISHED else None
        check = await self.render_check(user, run_id)
        confirmation = self.store.load_confirmation(user, run_id)
        options = self.generate.choice_options()
        attention = self._evidence_attention(user, run_id, version) if version else None
        proposed = {s.key: list(s.choices) for s in version.sections} if version else {}
        return submit_check(
            state=state,
            version=version,
            problems=state.problems,
            rules=self.generate.rules,
            confirmed=confirmation.choices if confirmation else {},
            overflow=check.overflow,
            evidence_counts=evidence_counts(version.sections, version.evidence_decisions)
            if version
            else {"total": 0},
            strategy_source=self.usability.strategy_source,
            strategy_options=len(options.get("strategy_alignment", {})),
            figures=list(version.figures) if version else [],
            figure_comments=self._open_figure_comments(user, run_id),
            evidence_attention=attention,
            proposed=proposed,
            choice_options=options,
        )

    def _evidence_attention(self, user: str, run_id: str, version: DraftVersion) -> dict[str, Any]:
        """항목 16 — 확인 필요 문장(Argon 불일치·부분 지지·이미지 판독 근거)과 일괄 승인 수."""
        snapshot = self.store.load_snapshot(user, run_id)
        basis_of: dict[str, str | None] = {}
        for c in snapshot.chunks if snapshot else []:
            basis_of[c.chunk_id] = c.basis
            basis_of.setdefault(c.doc_id, c.basis)
        review = self.store.load_review(user, run_id, 1)
        support = dict(review.support) if review is not None and review.support else {}
        return evidence_attention(version.sections, version.evidence_decisions, support, basis_of)

    async def bulk_approve_evidence(
        self, user: str, run_id: str, *, base_version: int | None = None
    ) -> DraftVersion:
        """[근거 일괄 승인] — 확인 필요 문장을 뺀 나머지 문장의 판단 없는 근거를 모두 승인 → 새 버전
        (note "근거 일괄 승인"). 승인할 것이 없으면 현재 버전 그대로."""
        if not self.usability.evidence_decisions:
            raise FeatureDisabled(
                "근거 판단 저장이 꺼져 있습니다 (usability.yaml evidence_decisions)."
            )
        state = await self.status(user, run_id)
        if self.is_legacy(state):
            raise EditRejected(LEGACY_HINT.format(run_id=run_id))
        try:
            nxt = review_flow.transition(state.status, "edit")
        except InvalidTransition as exc:
            raise EditRejected(str(exc)) from exc
        current = self._current_version(user, run_id, state)
        if base_version is not None and base_version != current.version:
            raise VersionConflict(
                f"기준 버전 v{base_version} 과 현재 버전 v{current.version} 이 다릅니다 — "
                "최신 버전을 불러와 다시 승인하십시오."
            )
        attention = self._evidence_attention(user, run_id, current)
        decisions = bulk_approvals(
            current.sections, current.evidence_decisions, attention["sentences"]
        )
        if not decisions:
            return current
        snapshot = self.store.load_snapshot(user, run_id)
        allowed = snapshot.retrieved_ids if snapshot else set()
        try:
            sections, merged = apply_decisions(
                current.sections, current.evidence_decisions, decisions, allowed
            )
        except DecisionRejected as exc:
            raise EditRejected(str(exc)) from exc
        new_version = DraftVersion(
            version=current.version + 1,
            origin="edit",
            sections=sections,
            created_at=self._clock(),
            note=f"근거 일괄 승인 {len(decisions)}건",
            changed_sections=changed_sections(current.sections, sections),
            annotations=current.annotations,
            evidence_decisions=merged,
            figures=list(current.figures),
        )
        self._store_version(user, run_id, state, new_version, nxt)
        return self.store.load_version(user, run_id, new_version.version) or new_version

    def _open_figure_comments(self, user: str, run_id: str) -> int:
        rounds = self.store.list_reviews(user, run_id)
        if not rounds:
            return 0
        latest = self.store.load_review(user, run_id, rounds[-1])
        if latest is None:
            return 0
        return sum(1 for c in latest.comments if c.kind == "figure" and c.status == "open")

    # ── [G] 그림 ─────────────────────────────────────────
    async def _figures_step(
        self,
        user: str,
        run_id: str,
        state: RunState,
        sections: list[Section],
        req: ProposalRequest,
        snapshot: RetrievalSnapshot | None,
    ) -> None:
        """v1 저장 직후 — 명세·밑그림·Nano Banana → 그림 파일(해시) 저장, v1.figures 갱신.
        실패해도 run 은 계속된다(step error 기록)."""
        if self.figures is None:
            return
        try:
            step = self._begin(state, FIGURES)
        except KeyError:
            return
        self._save(state)
        try:
            # 로컬 작성 run 은 전역 슬롯을 이미 잡고 있다 — 그림의 로컬 대체가 다시 잡지 않게
            held = not self._generate_for(state).writes_remotely
            # v2: 기본 그림(As-Is/To-Be + 수치 그래프·일정표)과 기법 추천(0~2)을 함께 — 최대 4장
            slots = figure_rules.technique_slots(len(self.figures.plan(sections, req, snapshot)))
            (builds, skipped), (tech_builds, outcome) = await asyncio.gather(
                self.figures.build_default(sections, req, snapshot, local_held=held),
                self._recommend_safely(
                    sections, req, snapshot, slots=slots, scope=state.scope, local_held=held
                ),
            )
            state.figure_techniques = outcome.model_dump()
            builds = [*builds, *tech_builds]
            for b in builds:
                self._save_build(user, run_id, b)
            v1 = self.store.load_version(user, run_id, 1)
            if v1 is not None:
                v1 = v1.model_copy(update={"figures": [b.figure for b in builds]})
                self.store.save_version(user, run_id, v1)
                state.figures = _figure_summary(v1.figures, [])
            for item in skipped:
                logger.info(
                    "figure.skipped run=%s kind=%s reason=%s", run_id, item["kind"], item["reason"]
                )
            self._finish(
                state,
                step,
                None,
                sentences=len(builds),
                dropped=len(skipped),
                fallback=",".join(sorted({b.figure.renderer for b in builds})) or None,
            )
        except Exception as exc:  # 그림 실패는 초안을 막지 않는다
            step.status = "error"
            step.error = type(exc).__name__
            step.finished_at = self._clock()
            logger.warning("figure.step_failed run=%s error=%s", run_id, type(exc).__name__)

    async def _recommend_safely(
        self,
        sections: list[Section],
        req: ProposalRequest,
        snapshot: RetrievalSnapshot | None,
        *,
        slots: int,
        scope: str,
        local_held: bool = False,
        existing_ids: Sequence[str] = (),
        exclude: Sequence[str] = (),
    ) -> tuple[list[FigureBuild], TechniqueOutcome]:
        """[11] 분석 기법 추천 — 실패해도 기본 그림을 막지 않는다(결과 "호출 실패" + 사유 코드).
        공용 계정 run 은 internal 근거를 뺀다."""
        if self.figures is None:
            return [], TechniqueOutcome(status="off", reason="disabled", at=self._clock())
        try:
            return await self.figures.recommend_techniques(
                sections,
                req,
                snapshot,
                slots=slots,
                existing_ids=existing_ids,
                exclude=exclude,
                include_internal=scope != "public",
                local_held=local_held,
            )
        except Exception as exc:  # 렌더·저장 오류 — 사유 코드만
            logger.warning("figure.techniques_failed error=%s", type(exc).__name__)
            return [], TechniqueOutcome(
                status="failed", reason=type(exc).__name__, at=self._clock()
            )

    def technique_catalog(self) -> list[dict[str, Any]]:
        """[11] 분석 기법 목록 (화면 [다른 기법으로 바꾸기]·[다른 그림 추가])."""
        return self.figures.technique_catalog_rows() if self.figures is not None else []

    async def figure_techniques(self, user: str, run_id: str) -> dict[str, Any] | None:
        """[11] 마지막 분석 기법 추천 결과 (빈 추천도 사유)."""
        return (await self.status(user, run_id)).figure_techniques

    async def retry_techniques(
        self, user: str, run_id: str, *, base_version: int | None = None
    ) -> tuple[DraftVersion | None, TechniqueOutcome]:
        """[11] [다시 추천] — 이미 있는 기법은 빼고 남은 자리(2 − 살아 있는 추천)만큼 다시 고른다.
        새 그림이 있으면 새 버전, 없으면 결과(해당 없음·호출 실패·규칙에 걸러짐)만 남긴다."""
        if self.figures is None:
            raise FeatureDisabled("그림 기능이 꺼져 있습니다 (figures.yaml enabled).")
        state, current, nxt = await self._figure_edit_base(user, run_id, base_version)
        alive = [
            f
            for f in current.figures
            if f.kind == "technique"
            and not (f.recommendation and f.recommendation.status == "dismissed")
        ]
        slots = figure_rules.MAX_TECHNIQUES - len(alive)
        if slots <= 0:
            raise EditRejected(
                "분석 기법 그림이 이미 2장입니다 — [필요 없음]으로 뺀 뒤 다시 추천받으십시오."
            )
        builds, outcome = await self._recommend_safely(
            current.sections,
            self.store.load_request(user, run_id),
            self.store.load_snapshot(user, run_id),
            slots=slots,
            scope=state.scope,
            existing_ids=[f.id for f in current.figures],
            exclude=[
                getattr(f.spec, "technique", "") for f in current.figures if f.kind == "technique"
            ],
        )
        state.figure_techniques = outcome.model_dump()
        if not builds:
            self._save(state)
            return None, outcome
        for b in builds:
            self._save_build(user, run_id, b)
        figures = [*current.figures, *(b.figure for b in builds)]
        version = self._store_figures(
            user, run_id, state, current, figures, nxt, note="분석 기법 추천"
        )
        return version, outcome

    def _save_build(self, user: str, run_id: str, build: FigureBuild) -> None:
        fig = build.figure
        if build.baseline_png and fig.baseline_sha:
            self.store.save_figure_image(
                user, run_id, fig.baseline_sha, build.baseline_png, "image/png"
            )
        if fig.image_sha:
            self.store.save_figure_image(
                user, run_id, fig.image_sha, build.adopted, build.adopted_mime
            )

    async def figure_image(self, user: str, run_id: str, sha: str) -> tuple[bytes, str] | None:
        await self.status(user, run_id)  # 소유자·존재 검사
        return self.store.load_figure_image(user, run_id, sha)

    async def add_figure(
        self,
        user: str,
        run_id: str,
        kind: str,
        section: str,
        *,
        base_version: int | None = None,
        technique: str = "",
    ) -> DraftVersion:
        """[다른 그림 추가] — 종류·섹션을 골라 명세·그림을 만들고 새 버전. kind=technique 면
        technique(기법 key)로 분석해 그린다(추천 배지 없음 — 제안자가 고른 그림)."""
        if self.figures is None:
            raise FeatureDisabled("그림 기능이 꺼져 있습니다 (figures.yaml enabled).")
        state, current, nxt = await self._figure_edit_base(user, run_id, base_version)
        req = self.store.load_request(user, run_id)
        snapshot = self.store.load_snapshot(user, run_id)
        if kind == "technique":
            if self.figures.catalog.get(technique) is None:
                raise EditRejected("분석 기법을 골라 주십시오.")
            build, reason = await self.figures.build_technique(
                technique,
                section or None,
                current.sections,
                req,
                snapshot,
                existing_ids=[f.id for f in current.figures],
                include_internal=state.scope != "public",
            )
            if build is None:
                raise EditRejected(_technique_reject(reason))
            self._save_build(user, run_id, build)
            figures = [*current.figures, build.figure]
            return self._store_figures(user, run_id, state, current, figures, nxt, note="그림 추가")
        builds, skipped = await self.figures.build_all(
            [(kind, section)],
            current.sections,
            req,
            snapshot,
            existing_ids=[f.id for f in current.figures],
        )
        if not builds:
            reason = skipped[0]["reason"] if skipped else "invalid"
            raise EditRejected(f"그림 명세를 만들지 못했습니다 ({reason}).")
        for b in builds:
            self._save_build(user, run_id, b)
        figures = [*current.figures, *(b.figure for b in builds)]
        return self._store_figures(user, run_id, state, current, figures, nxt, note="그림 추가")

    async def figure_action(
        self,
        user: str,
        run_id: str,
        figure_id: str,
        action: str,
        *,
        request_text: str = "",
        texts: Mapping[str, str] | None = None,
        base_version: int | None = None,
        technique: str = "",
    ) -> DraftVersion:
        """그림 카드 동작 — words(말로 고치기) | texts(글자 고치기) | baseline(기본 그림으로) |
        regenerate(다시 만들기) | include | exclude | confirm | [11] accept(넣기 확정) |
        dismiss(필요 없음) | restore(다시 넣기) | swap(다른 기법으로 바꾸기, technique 필수).
        저장은 새 버전(되돌리기 가능) — 추천 결정도 버전 변경("변경 n건")으로 센다."""
        if self.figures is None:
            raise FeatureDisabled("그림 기능이 꺼져 있습니다 (figures.yaml enabled).")
        state, current, nxt = await self._figure_edit_base(user, run_id, base_version)
        by_id = {f.id: f for f in current.figures}
        fig = by_id.get(figure_id)
        if fig is None:
            raise EditRejected("그림이 없습니다.")
        note = f"그림 {action}"
        rec = fig.recommendation
        if action in ("include", "exclude") and rec is not None:
            action = "restore" if action == "include" else "dismiss"  # 추천 그림은 결정으로 남긴다
            note = f"그림 {action}"
        if action in ("include", "exclude"):
            fig = fig.model_copy(update={"included": action == "include"})
        elif action in ("accept", "dismiss", "restore"):
            if rec is None:
                raise EditRejected("추천 그림이 아닙니다.")
            status = "dismissed" if action == "dismiss" else "accepted"
            fig = fig.model_copy(
                update={
                    "recommendation": rec.model_copy(
                        update={"status": status, "at": self._clock()}
                    ),
                    "included": action != "dismiss",
                }
            )
        elif action == "swap":
            if fig.kind != "technique":
                raise EditRejected("분석 기법 그림만 다른 기법으로 바꿀 수 있습니다.")
            old_key = getattr(fig.spec, "technique", "")
            if self.figures.catalog.get(technique) is None or technique == old_key:
                raise EditRejected("바꿀 분석 기법을 목록에서 골라 주십시오.")
            new_rec = (
                FigureRecommendation(
                    technique=technique,
                    reason="제안자가 고른 기법",
                    status="pending",
                    swapped_from=old_key,
                    at=self._clock(),
                )
                if rec is not None
                else None
            )
            build, reason = await self.figures.build_technique(
                technique,
                fig.section,
                current.sections,
                self.store.load_request(user, run_id),
                self.store.load_snapshot(user, run_id),
                figure_id=fig.id,
                recommendation=new_rec,
                include_internal=state.scope != "public",
            )
            if build is None:
                raise EditRejected(_technique_reject(reason))
            self._save_build(user, run_id, build)
            fig = build.figure.model_copy(update={"included": True})
        elif action == "confirm":
            fig = fig.model_copy(update={"confirmed": True})
        elif action == "baseline":
            build = self.figures.baseline(fig)
            self._save_build(user, run_id, build)
            fig = build.figure
        elif action == "regenerate":
            build = await self.figures.draw(fig)
            self._save_build(user, run_id, build)
            fig = build.figure
        elif action == "texts":
            try:
                spec = figure_rules.apply_text_edits(fig.spec, dict(texts or {}))
            except ValueError as exc:
                raise EditRejected(str(exc)) from exc
            summary = figure_rules.spec_change_summary(fig.spec, spec)
            fig = fig.model_copy(update={"spec": spec, "alt": figure_rules.alt_text(spec)})
            build = await self.figures.draw(fig)
            self._save_build(user, run_id, build)
            fig = build.figure.model_copy(
                update={
                    "last_change": FigureChange(kind="content", summary=summary, at=self._clock())
                }
            )
        elif action == "words":
            if not request_text.strip():
                raise EditRejected("수정 요청이 비어 있습니다.")
            # 요청 → 명세 변경 → 밑그림 → 새로 그림 (현재 그림은 보내지 않는다, 2026-10-28 [2])
            try:
                build = await self.figures.edit_by_words(
                    fig,
                    request_text,
                    sections=current.sections,
                    request=self.store.load_request(user, run_id),
                    snapshot=self.store.load_snapshot(user, run_id),
                )
            except SpecRejected as exc:
                raise EditRejected(
                    f"그림을 고치지 못했습니다 ({exc}). {_edit_reject_hint(str(exc))}".rstrip()
                ) from exc
            self._save_build(user, run_id, build)
            fig = build.figure
        else:
            raise EditRejected(f"알 수 없는 동작입니다: {action}")
        figures = [fig if f.id == figure_id else f for f in current.figures]
        return self._store_figures(user, run_id, state, current, figures, nxt, note=note)

    async def _figure_edit_base(
        self, user: str, run_id: str, base_version: int | None
    ) -> tuple[RunState, DraftVersion, str]:
        state = await self.status(user, run_id)
        if self.is_legacy(state):
            raise EditRejected(LEGACY_HINT.format(run_id=run_id))
        try:
            nxt = review_flow.transition(state.status, "edit")
        except InvalidTransition as exc:
            raise EditRejected(str(exc)) from exc
        current = self._current_version(user, run_id, state)
        if base_version is not None and base_version != current.version:
            raise VersionConflict(
                f"기준 버전 v{base_version} 과 현재 버전 v{current.version} 이 다릅니다 — "
                "최신 버전을 불러와 다시 시도하십시오."
            )
        return state, current, nxt

    def _store_figures(
        self,
        user: str,
        run_id: str,
        state: RunState,
        current: DraftVersion,
        figures: list[Figure],
        status: str,
        *,
        note: str,
    ) -> DraftVersion:
        new_version = DraftVersion(
            version=current.version + 1,
            origin="edit",
            sections=current.sections,
            created_at=self._clock(),
            note=note,
            changed_sections=sorted(
                {f.section for f in figure_rules_changed(current.figures, figures)}
            ),
            annotations=current.annotations,
            evidence_decisions=current.evidence_decisions,
            figures=figures,
        )
        self._store_version(user, run_id, state, new_version, status)
        return self.store.load_version(user, run_id, new_version.version) or new_version

    # ── U8 시범운영 측정 ─────────────────────────────────
    def _touch_usage(
        self,
        user: str,
        run_id: str,
        state: RunState,
        *,
        counts: dict[str, int] | None = None,
        checklist_coverage: float | None = None,
        rewrites_add: int = 0,
        hwpx_success: bool | None = None,
    ) -> UsageRecord | None:
        if not self.usability.usage_record:
            return None
        record = self.store.load_usage(user, run_id) or UsageRecord(run_id=run_id)
        record = refresh_usage(record, state, counts=counts, now=self._clock())
        update: dict[str, Any] = {"gemini_calls": self._gemini_calls(user, run_id, state)}
        if checklist_coverage is not None:
            update["checklist_coverage"] = float(checklist_coverage)
        if rewrites_add:
            update["rewrites"] = record.rewrites + rewrites_add
        if hwpx_success is not None:
            update["hwpx_success"] = hwpx_success
        record = record.model_copy(update=update)
        self.store.save_usage(user, run_id, record)
        return record

    def _gemini_calls(self, user: str, run_id: str, state: RunState) -> dict[str, int]:
        """초안 한 건의 Gemini 호출 수 — 작성·검토(차수 합)·그림
        (domain/rules/writer.gemini_calls)."""
        reviews = [
            r
            for n in self.store.list_reviews(user, run_id)
            if (r := self.store.load_review(user, run_id, n)) is not None
        ]
        return gemini_calls(
            state.writers,
            state.fallback_sections,
            [r.transfer.calls for r in reviews],
            state.figures,
        )

    async def usage(self, user: str, run_id: str) -> UsageRecord | None:
        state = await self.status(user, run_id)
        record = self.store.load_usage(user, run_id)
        if record is None:
            return self._touch_usage(user, run_id, state)
        # 단계 시간은 읽을 때 다시 계산한다 — 섹션 작성은 벽시계(2026-10-28 규칙)로
        return record.model_copy(
            update={
                "step_seconds": usage_step_durations(state),
                "total_seconds": usage_total_seconds(state),
            }
        )

    async def feedback(self, user: str, run_id: str, score: int, comment: str = "") -> UsageRecord:
        """마무리 뒤 만족도(1~5 + 한 줄). 개인정보 없음(이메일·전화 금지, 200자)."""
        if not self.usability.feedback:
            raise FeatureDisabled("만족도 기록이 꺼져 있습니다 (usability.yaml feedback).")
        state = await self.status(user, run_id)
        if state.status != "finalized":
            raise FeedbackRejected("만족도는 최종 마무리(finalized) 뒤에 기록합니다.")
        satisfaction = Satisfaction(score=score, comment=comment, recorded_at=self._clock())
        record = self.store.load_usage(user, run_id) or UsageRecord(run_id=run_id)
        record = refresh_usage(record, state, now=self._clock()).model_copy(
            update={"satisfaction": satisfaction}
        )
        self.store.save_usage(user, run_id, record)
        self._record(state)
        return record

    # ── ⑥ 최종 마무리·다시 열기 ───────────────────────
    async def finalize(
        self,
        user: str,
        run_id: str,
        *,
        choices: Mapping[str, list[str]] | None = None,
        proposer: ProposerInfo | None = None,
        version: int | None = None,
    ) -> FinalizeResult:
        """선택형 확정(제안값이 기본) + 제안자 정보 + render_check → finalized → HWPX.

        조건: 최종 검토 완료(또는 검토 LLM 이 없어 건너뜀), 검토 중 아님, 임시 편집 없음.
        stale(최종 검토 이후 수정)이면 점검 맨 위에 경고만. version 을 주면 그 버전으로 마무리한다.
        제안자 정보·제안부서·제안일자는 렌더 인자로만 쓰고 저장하지 않는다. 다시 마무리하면 새 파일.
        """
        if self.renderer is None:
            raise RenderUnavailable("렌더러가 설정되지 않았습니다 (uv pip install -e '.[render]').")
        state = await self.status(user, run_id)
        if self.is_legacy(state):
            raise FinalizeRejected(LEGACY_HINT.format(run_id=run_id))
        if not review_flow.can_finalize(
            state.status,
            final_reviewed=state.final_reviews > 0,
            review_skipped=state.review_skipped,
        ):
            raise FinalizeRejected(
                f"{state.status} 상태에서는 마무리할 수 없습니다 — 최종 검토 완료(또는 건너뜀) 뒤, "
                "검토 중이 아닐 때만."
            )
        if self.store.load_working(user, run_id) is not None:
            raise FinalizeRejected(
                "저장하지 않은 임시 편집이 있습니다 — 먼저 저장하거나 버리십시오."
            )
        view = await self.get_draft(user, run_id)
        sections = view.sections
        picked = view.version
        if version is not None and version != view.version:
            chosen = await self.get_version(user, run_id, version)
            sections, picked = chosen.sections, chosen.version
        confirmation = await self._confirm_for_finalize(user, run_id, view, choices)
        check = await self.render_check(user, run_id, proposer=proposer)
        if state.stale:
            check = replace(
                check,
                notes=[
                    f"최종 검토 이후 수정 {state.stale_edits}건 — 다시 받기는 선택",
                    *check.notes,
                ],
            )
        draft = Draft(
            run_id=run_id,
            request=self.store.load_request(user, run_id),
            sections=sections,
            template=state.template,
        )
        figure_files = self._figure_files(user, run_id, picked)
        placements: list[FigurePlacement] = []
        try:
            if figure_files and hasattr(self.renderer, "render_with_figures"):
                data, placements = self.renderer.render_with_figures(
                    draft, confirmation=confirmation, proposer=proposer, figures=figure_files
                )
            else:
                data = self.renderer.render(draft, confirmation=confirmation, proposer=proposer)
        except Exception:
            self._touch_usage(user, run_id, state, hwpx_success=False)
            raise
        fmt = getattr(self.renderer, "last_format", None)  # 동기 렌더 바로 뒤 — 이 호출의 결과
        state = await self.status(user, run_id)
        state.hwpx_format = dict(fmt) if fmt else None
        if fmt:
            logger.info(
                "run.hwpx_format run=%s fixed=%d remaining=%d paragraphs=%d",
                run_id,
                int(fmt.get("fixed_total") or 0),
                sum((fmt.get("remaining") or {}).values()),
                int(fmt.get("paragraphs") or 0),
            )
        if placements:
            by_id = {p.id: p for p in placements}
            state.figures = [
                {**row, "placement": by_id[row["id"]].placement, "number": by_id[row["id"]].number}
                if row.get("id") in by_id
                else row
                for row in state.figures
            ]
        state.status = review_flow.transition(state.status, "finalize")
        state.finalized_at = self._clock()
        self._touch_usage(user, run_id, state, hwpx_success=True)
        self._save(state)
        return FinalizeResult(
            data=data,
            confirmation=confirmation,
            check=check,
            version=picked,
            state=state,
            title=draft_title(sections, draft.request),
            hwpx_format=state.hwpx_format,
        )

    def run_title(self, state: RunState) -> str:
        """화면 머리·run 목록의 연구과제명 — 현재 버전의 1-가 문장, 없으면 저장된 섹션, 그것도
        없으면 가제(title_hint). 읽기 실패는 빈 문자열 (화면이 "제목 미정")."""
        try:
            version = (
                self.store.load_version(state.user, state.run_id, state.draft_version)
                if state.draft_version >= 1
                else None
            )
            sections = (
                list(version.sections)
                if version is not None
                else list(self.store.load_sections(state.user, state.run_id).values())
            )
            request = self.store.load_request(state.user, state.run_id)
        except Exception:  # noqa: BLE001 — 제목 표시는 run 조회를 막지 않는다
            return ""
        return draft_title(sections, request)

    def _figure_files(
        self, user: str, run_id: str, version_no: int
    ) -> list[tuple[Figure, bytes, str]]:
        """그 버전에서 제안서에 넣는 그림(included)의 (Figure, 바이트, mime). 파일 없으면 건너뜀."""
        version = self.store.load_version(user, run_id, version_no)
        out: list[tuple[Figure, bytes, str]] = []
        order = {s.key: i for i, s in enumerate(version.sections)} if version else {}
        figures = sorted(
            version.figures if version else [],
            key=lambda f: (order.get(f.section, len(order)), f.id),
        )  # "그림 n" 은 양식에 나오는 섹션 순서대로
        for fig in figures:
            if not fig.included or not fig.image_sha:
                continue
            loaded = self.store.load_figure_image(user, run_id, fig.image_sha)
            if loaded is not None:
                out.append((fig, loaded[0], loaded[1]))
        return out

    async def _confirm_for_finalize(
        self,
        user: str,
        run_id: str,
        view: DraftView,
        choices: Mapping[str, list[str]] | None,
    ) -> Confirmation:
        """주어진 선택값을 확정하고, 비어 있는 선택형 항목은 LLM 제안값으로 채운다."""
        merged = dict(view.confirmation.choices if view.confirmation else {})
        for key, values in (choices or {}).items():
            merged[key] = list(values)
        for sec in view.sections:
            spec = self.generate.rules.choices.get(sec.key)
            if spec is None or merged.get(sec.key):
                continue
            proposed = [c for c in sec.choices if c in view.choice_options.get(sec.key, {})]
            if proposed and max(spec.min, 1) <= len(proposed) <= spec.max:
                merged[sec.key] = proposed[: spec.max]
        if not merged:
            raise ConfirmRejected("확정할 선택값이 없습니다 (과제유형·활용계획을 고르십시오).")
        return await self.confirm(user, run_id, merged)

    async def reopen(self, user: str, run_id: str) -> RunState:
        state = await self.status(user, run_id)
        try:
            state.status = review_flow.transition(state.status, "reopen")
        except InvalidTransition as exc:
            raise EditRejected(str(exc)) from exc
        self._save(state)
        return state

    # ── 양식 렌더 (Step 8) ───────────────────────────────
    async def render_check(
        self, user: str, run_id: str, *, proposer: ProposerInfo | None = None
    ) -> RenderCheck:
        """렌더 전 점검 — 미해결 lint 알림, 칸 길이 초과, 전략 빈칸. 렌더를 막지 않는다.

        proposer 는 길이만 재고 저장하지 않는다 (렌더와 같은 규칙).
        """
        view = await self.get_draft(user, run_id)
        draft = Draft(
            run_id=run_id,
            request=self.store.load_request(user, run_id),
            sections=view.sections,
            template=view.state.template,
        )
        return render_check(
            draft,
            view.state.problems,
            self.generate.rules,
            confirmation=view.confirmation,
            proposer=proposer,
            line_limits=self.line_limits,
            strategy_labels=view.choice_options.get("strategy_alignment", {}),
            failed_sections=view.state.failed_sections,
        )

    async def render(
        self, user: str, run_id: str, *, proposer: ProposerInfo | None = None
    ) -> bytes:
        """이미 마무리(finalized)된 run 의 양식 파일을 다시 만든다. 그 밖의 상태는 거부 —
        양식 파일은 finalize 로만 만든다 (domain/rules/review_flow.can_render).

        제안자 정보는 저장하지 않는다 (run 폴더·manifest·로그 어디에도).
        """
        if self.renderer is None:
            raise RenderUnavailable("렌더러가 설정되지 않았습니다 (uv pip install -e '.[render]').")
        view = await self.get_draft(user, run_id)
        if view.legacy:
            raise RenderRejected(LEGACY_HINT.format(run_id=run_id))
        if not review_flow.can_render(view.state.status):
            raise RenderRejected(
                f"{view.state.status} 상태의 run 은 렌더할 수 없습니다 — 양식 파일은 finalize 로만."
            )
        draft = Draft(
            run_id=run_id,
            request=self.store.load_request(user, run_id),
            sections=view.sections,
            template=view.state.template,
        )
        return self.renderer.render(draft, confirmation=view.confirmation, proposer=proposer)

    # ── 선택값 확정 ───────────────────────────────────────
    async def confirm(self, user: str, run_id: str, choices: dict[str, list[str]]) -> Confirmation:
        """과제유형·활용계획·전략 선택을 사용자가 확정한다. 기존 확정값에 키 단위로 덮어쓴다."""
        state = await self.status(user, run_id)
        if self.is_legacy(state):
            raise ConfirmRejected(LEGACY_HINT.format(run_id=run_id))
        if state.status not in FINISHED or state.status == "failed":
            raise ConfirmRejected(f"{state.status} 상태의 run 은 확정할 수 없습니다 (생성 후에).")
        if not choices:
            raise ConfirmRejected("확정할 선택값이 없습니다.")
        options = self.generate.choice_options()
        current = self.store.load_confirmation(user, run_id) or Confirmation()
        merged = dict(current.choices)
        for key, values in choices.items():
            spec = self.generate.rules.choices.get(key)
            if spec is None:
                raise ConfirmRejected(f"선택형 항목이 아닙니다: {key}")
            picked = list(dict.fromkeys(values))
            unknown = [v for v in picked if v not in options.get(key, {})]
            if unknown:
                raise ConfirmRejected(f"{key}: 선택지에 없는 값 {unknown}")
            if not max(spec.min, 1) <= len(picked) <= spec.max:
                raise ConfirmRejected(
                    f"{key}: {max(spec.min, 1)}~{spec.max}개를 골라야 합니다 ({len(picked)}개)."
                )
            merged[key] = picked
        confirmation = Confirmation(choices=merged, updated_at=self._clock())
        self.store.save_confirmation(user, run_id, confirmation)
        self._record(state)
        return confirmation

    # ── 항목 17 ①·② 입력 변경 → 관련 섹션만 / 전체 다시 쓰기 ─────────────
    async def run_inputs(self, user: str, run_id: str) -> dict[str, Any]:
        """단계 표시 ①·② 를 run 안에서 열 때 — 저장된 입력·② 우선 근거·현재 버전·상태."""
        state = await self.status(user, run_id)
        req = self.store.load_request(user, run_id)
        notes = self.store.load_notes(user, run_id) or {}
        return {
            "request": req.model_dump(mode="json"),
            "priority_evidence": [str(x) for x in notes.get("priority_evidence") or []],
            "draft_version": state.draft_version,
            "status": state.status,
        }

    async def request_change_preview(
        self,
        user: str,
        run_id: str,
        req: ProposalRequest,
        *,
        priority_evidence: list[str] | None = None,
    ) -> dict[str, Any]:
        """저장 전에 — 바뀐 입력 칸·관련 섹션·다시 쓸 수 있는 상태인지 (저장하지 않는다)."""
        state = await self.status(user, run_id)
        old = self.store.load_request(user, run_id)
        notes = self.store.load_notes(user, run_id) or {}
        fields = changed_fields(
            old.model_dump(mode="json"),
            req.model_dump(mode="json"),
            old_priority=[str(x) for x in notes.get("priority_evidence") or []],
            new_priority=priority_evidence,
        )
        keys = list(self.generate.section_keys)
        affected = affected_sections(
            fields, keys, evidence_sections=self.generate.rules.evidence_required
        )
        reason = None
        if self.is_legacy(state):
            reason = "이전 양식으로 만든 run 은 다시 쓸 수 없습니다."
        elif state.draft_version < 1 or not review_flow.can_edit(state.status):
            reason = "초안이 완성된 뒤(검토 중이 아닐 때) 다시 쓸 수 있습니다."
        elif self.store.load_working(user, run_id) is not None:
            reason = "저장하지 않은 임시 편집이 있습니다 — 먼저 저장하거나 버리십시오."
        return {
            "fields": fields,
            "sections": affected,
            "all_sections": keys,
            "can_regenerate": reason is None,
            "reason": reason,
            "version": state.draft_version,
        }

    async def regenerate(
        self,
        user: str,
        run_id: str,
        req: ProposalRequest,
        *,
        mode: str = "sections",
        base_version: int | None = None,
        priority_evidence: list[str] | None = None,
    ) -> RegenerateResult:
        """바뀐 입력으로 새 버전을 만든다.

        mode=sections 는 관련 섹션만 (U3 다시 쓰기와 같은 길 — 제안자 수정·입력 문장은 그 자리에
        둔다), all 은 모든 섹션을 새로 쓴다 (이전 초안은 이전 버전으로 남는다). 섹션 작성은 생성과
        같은 길이다 — Argon 먼저·실패하면 로컬, 로컬은 슬롯 안에서. 근거 집합은 다시 검색하지
        않는다 (보안 A 대조 집합 유지). 다시 쓰지 못한 섹션은 이전 내용을 두고 failed 로 알린다
        (빈칸으로 바꾸지 않는다). 전부 실패하면 EditRejected (입력도 저장하지 않는다).
        """
        if mode not in ("sections", "all"):
            raise EditRejected(f"알 수 없는 다시 쓰기 방식: {mode}")
        state = await self.status(user, run_id)
        if self.is_legacy(state):
            raise EditRejected(LEGACY_HINT.format(run_id=run_id))
        try:
            nxt = review_flow.transition(state.status, "edit")
        except InvalidTransition as exc:
            raise EditRejected(str(exc)) from exc
        if state.draft_version < 1:
            raise EditRejected("초안이 완성된 뒤 다시 쓸 수 있습니다.")
        if self.store.load_working(user, run_id) is not None:
            raise EditRejected("저장하지 않은 임시 편집이 있습니다 — 먼저 저장하거나 버리십시오.")
        current = self._current_version(user, run_id, state)
        if base_version is not None and base_version != current.version:
            raise VersionConflict(
                f"기준 버전 v{base_version} 과 현재 버전 v{current.version} 이 다릅니다 — "
                "최신 버전을 불러와 다시 저장하십시오."
            )
        preview = await self.request_change_preview(
            user, run_id, req, priority_evidence=priority_evidence
        )
        fields: list[str] = list(preview["fields"])
        keys = list(self.generate.section_keys)
        targets = regen_targets(mode, preview["sections"], keys)  # type: ignore[arg-type]
        if not fields and mode == "sections":
            return RegenerateResult(current, mode, [], [], [], [])
        notes = self.store.load_notes(user, run_id) or {}
        if not targets:  # 양식 칸(제안부서·예산)만 바뀜 — 입력만 저장, 새 버전 없음
            self.store.save_request(user, run_id, req)
            self._note_request_change(user, run_id, notes, fields, mode, current.version)
            return RegenerateResult(current, mode, fields, [], [], [], saved_only=True)

        claim = self.store.claim(user, run_id)  # 생성·검토가 이 run 을 잡고 있으면 RunBusy
        try:
            snapshot = self.store.load_snapshot(user, run_id)
            if snapshot is None:
                raise EditRejected("검색 스냅샷이 없어 다시 쓸 수 없습니다.")
            if priority_evidence is not None:
                ids = [str(x)[:200] for x in priority_evidence if str(x).strip()][:50]
                notes = {**notes, "priority_evidence": ids}
                self.store.save_notes(user, run_id, notes)
                snapshot = self._prioritize(user, run_id, snapshot)
                self.store.save_snapshot(user, run_id, snapshot)
            answers = notes.get("answers") or {}
            gen = self._generate_for(state)  # 공용 계정 run 은 internal 제외 유스케이스
            composed_by_key: dict[str, Any] = {}
            failed: list[dict[str, str]] = []
            kept: list[str] = []

            async def one(key: str) -> None:
                existing = current.section(key) or Section(key=key, sentences=[])
                try:
                    if mode == "sections":
                        out = await gen.rewrite_section(
                            key, req, snapshot, existing, notes=answers.get(key) or {}
                        )
                    else:
                        out = await gen.compose_section(key, req, snapshot)
                except ValueError:  # 앱이 쓰는 섹션(특이사항) — 그대로 둔다
                    kept.append(key)
                    return
                except Exception as exc:  # noqa: BLE001 — 그 섹션만 이전 내용 유지
                    failed.append({"key": key, "reason": type(exc).__name__})
                    return
                composed_by_key[key] = out

            async with self._run_gate(gen):
                limit = max(1, int(gen.compose_concurrency)) if gen.writes_remotely else 1
                sem = asyncio.Semaphore(limit)

                async def bounded(key: str) -> None:
                    async with sem:
                        await one(key)

                await asyncio.gather(*(bounded(k) for k in targets))

            sections: list[Section] = []
            regenerated: list[str] = []
            for sec in current.sections:
                out = composed_by_key.get(sec.key)
                if out is None:
                    sections.append(sec)
                    continue
                candidate = _cleaned(out.section)
                if not candidate.sentences and sec.sentences and out.mode not in ("skipped", "app"):
                    failed.append({"key": sec.key, "reason": out.mode or "empty"})
                    sections.append(sec)  # 빈 결과로 덮지 않는다
                    continue
                if not candidate.sentences and out.mode == "skipped" and sec.sentences:
                    kept.append(sec.key)  # 입력이 비어 생략 — 이전 문장 유지
                    sections.append(sec)
                    continue
                sections.append(candidate)
                regenerated.append(sec.key)
            for key in targets:  # 이전 버전에 없던 섹션
                if key not in {s.key for s in current.sections} and key in composed_by_key:
                    sections.append(_cleaned(composed_by_key[key].section))
                    regenerated.append(key)
            if not regenerated:
                raise EditRejected(
                    "다시 쓴 섹션이 없습니다 — 모델 응답이 없거나 형식이 맞지 않았습니다. "
                    "잠시 뒤 다시 시도하거나 직접 수정하십시오."
                )
            draft, _problems = self.generate.finalize(run_id, req, snapshot, sections)
            tidy = {s.key: s for s in draft.sections}  # Q6 자동 정리 — 다시 쓴 섹션에만
            sections = [tidy.get(s.key, s) if s.key in regenerated else s for s in sections]

            latest = await self.status(user, run_id)
            if latest.draft_version != current.version:
                raise VersionConflict(
                    "다시 쓰는 동안 새 버전이 저장되었습니다 — 다시 시도하십시오."
                )
            for key in regenerated:
                writer = getattr(composed_by_key.get(key), "writer", None)
                if writer:
                    latest.writers[key] = dict(writer)
            labels = ", ".join(FIELD_LABELS.get(f, f) for f in fields) or "입력"
            new_version = DraftVersion(
                version=current.version + 1,
                origin="regenerate",
                sections=sections,
                created_at=self._clock(),
                note=f"{MODE_NOTES[mode]} ({labels})"[:200],
                changed_sections=changed_sections(current.sections, sections),
                annotations=[a for a in current.annotations if a.section not in regenerated],
                evidence_decisions=decisions_for_sections(sections, current.evidence_decisions),
                figures=list(current.figures),
            )
            self.store.save_request(user, run_id, req)
            self._note_request_change(user, run_id, notes, fields, mode, new_version.version)
            self._store_version(user, run_id, latest, new_version, nxt)
            self._touch_usage(user, run_id, latest, rewrites_add=1)
            if failed:
                logger.warning(
                    "run.regenerate_partial run=%s failed=%s",
                    run_id,
                    ",".join(f"{f['key']}:{f['reason']}" for f in failed),
                )
            stored = self.store.load_version(user, run_id, new_version.version) or new_version
            return RegenerateResult(stored, mode, fields, regenerated, failed, kept)
        finally:
            claim.release()

    def _note_request_change(
        self,
        user: str,
        run_id: str,
        notes: dict[str, Any],
        fields: list[str],
        mode: str,
        version: int,
    ) -> None:
        """입력 변경 이력 — 칸 이름·방식·버전만 (본문 없음)."""
        history = list(notes.get("request_history") or [])[-49:]
        history.append({"at": self._clock(), "fields": fields, "mode": mode, "version": version})
        self.store.save_notes(user, run_id, {**notes, "request_history": history})

    async def _citations(
        self, sections: list[Section], snapshot: RetrievalSnapshot | None
    ) -> list[Citation]:
        if snapshot is None:
            return []
        doc_of = {c.chunk_id: c.doc_id for c in snapshot.chunks}
        doc_of.update({c.doc_id: c.doc_id for c in snapshot.chunks})
        out: list[Citation] = []
        seen: set[str] = set()
        for ev in (e for s in sections for sent in s.sentences for e in sent.evidence):
            if ev in seen or ev not in doc_of:
                continue
            seen.add(ev)
            doc = await self.generate.repo.get_document(doc_of[ev])
            out.append(Citation(id=ev, doc_id=doc_of[ev], title=doc.title if doc else None))
        return out


def manifest(
    state: RunState,
    snapshot: RetrievalSnapshot | None,
    confirmation: Confirmation | None = None,
    reviews: list[ReviewRound] | None = None,
    versions: list[DraftVersion] | None = None,
    usage: UsageRecord | None = None,
) -> dict[str, Any]:
    """보안 I: 해시·id·개수·클래스명만. 입력·문장·lint 메시지(문장 앞부분 포함)·의견 원문은 제외.

    검토는 차수별 provider·model, 외부 전송 doc_id(public/internal 구분), 보낸 문장 수만 남긴다.
    U8 usage 는 개수·성공 여부·점수만 (한 줄 소감은 남기지 않는다).
    """
    return {
        "run_id": state.run_id,
        "status": state.status,
        "model": state.model,
        "template": state.template,
        "created_at": state.created_at,
        "updated_at": state.updated_at,
        "query_hash": snapshot.query_hash if snapshot else None,
        "retrieved": sorted(snapshot.retrieved_ids) if snapshot else [],
        "steps": [
            {
                "name": s.name,
                "status": s.status,
                "started_at": s.started_at,
                "finished_at": s.finished_at,
                "error": s.error,
                "sentences": s.sentences,
                "dropped": s.dropped,
                "evidence": s.evidence,
                "prompt_hash": s.prompt_hash,
                "parse": s.parse,
                "raw_chars": s.raw_chars,
                "retries": s.retries,
                "fallback": s.fallback,
            }
            for s in state.steps
        ],
        "problems": [
            {
                "section": p["section"],
                "code": p["code"],
                "severity": p.get("severity", "error"),
            }
            for p in state.problems
        ],
        "confirmed": sorted(confirmation.choices) if confirmation else [],
        "draft_version": state.draft_version,
        "review": {
            "rounds": state.review_rounds,
            "skipped": state.review_skipped,
            "model": state.review_model,
            "error": state.review_error,
            "transfers": [
                {
                    "round": r.round,
                    "status": r.status,
                    "provider": r.transfer.provider,
                    "model": r.transfer.model,
                    "public_doc_ids": list(r.transfer.public_doc_ids),
                    "internal_doc_ids": list(r.transfer.internal_doc_ids),
                    "sentences_sent": r.transfer.sentences_sent,
                    "sentences_excluded": r.transfer.sentences_excluded,
                    "comments": len(r.comments),
                    "scores": {s.criterion: s.score for s in r.scores},
                    "kind": r.kind,
                    "applied": len(r.applied_ids),
                    "applied_version": r.applied_version,
                    "additions": sum(1 for c in r.comments if c.kind == "addition"),
                    "candidates": {k: v.get("choice") for k, v in r.candidate_choices.items()},
                    "checklist_coverage": r.checklist_coverage,
                    "support": len(getattr(r, "support", {}) or {}),
                }
                for r in reviews or []
            ],
            "final_reviews": state.final_reviews,
            "final_reviewed_version": state.final_reviewed_version,
            "stale_edits": state.stale_edits,
            "draft_review_skipped": state.draft_review_skipped,
        },
        "failed_sections": [{"key": f.key, "reason": f.reason} for f in state.failed_sections],
        "fallback_sections": [dict(x) for x in state.fallback_sections],
        # [3] ADR 0032 — 섹션 작성자·로컬 대체 사유·전송 doc_id·원격 호출 수 (본문 없음)
        "writer": state.writer,
        "writers": [{"key": k, **dict(w)} for k, w in state.writers.items()],
        "local_sections": local_sections(state.writers, state.section_keys),
        "local_check": None
        if state.local_check is None
        else {
            **(local_check_view(state.local_check) or {}),
            "sentences": int(state.local_check.get("sentences") or 0),
            "checked_sections": list(state.local_check.get("checked_sections") or []),
        },
        "gemini_calls": gemini_calls(
            state.writers,
            state.fallback_sections,
            [r.transfer.calls for r in reviews or []],
            state.figures,
        ),
        "versions": [
            {
                "version": v.version,
                "origin": v.origin,
                "changed_sections": len(v.changed_sections),
                "sentences": v.sentence_count,
                "alerts": v.alerts,
                "open_annotations": v.open_annotations,
                "decisions": len(getattr(v, "evidence_decisions", []) or []),
            }
            for v in versions or []
        ],
        "usage": None
        if usage is None
        else {
            "rewrites": usage.rewrites,
            "decisions": usage.evidence.approve + usage.evidence.replace + usage.evidence.exclude,
            "hwpx_success": usage.hwpx_success,
            "satisfaction_score": usage.satisfaction.score if usage.satisfaction else None,
        },
        "finalized_at": state.finalized_at,
        "differentiation": dict(state.differentiation) if state.differentiation else None,
        "recommendations": dict(state.recommendations) if state.recommendations else None,
        "figures": [dict(x) for x in state.figures],  # [G] 그림 요약 (본문 없음)
        "live_search": live_search_manifest(state),
        "hwpx_format": dict(state.hwpx_format) if state.hwpx_format else None,  # 건수만
    }


def live_search_manifest(state: RunState) -> dict[str, Any] | None:
    """[4] manifest 용 실시간 검색 요약 — 상태·자료원별 상태/건수/초·키워드 개수만 (키워드·안내 문구
    없음)."""
    live = state.live_search
    if not live:
        return None
    keywords = live.get("keywords") or {}
    return {
        "status": live.get("status"),
        "keywords": {"ko": len(keywords.get("ko") or []), "en": len(keywords.get("en") or [])},
        "sources": [
            {
                "source": r.get("source"),
                "status": r.get("status"),
                "count": r.get("count"),
                "new": r.get("new"),
                "seconds": r.get("seconds"),
                "cached": r.get("cached"),
            }
            for r in live.get("sources") or []
        ],
        "documents": len(state.live_doc_ids),
    }


_EDIT_REJECT_HINTS = {
    "figure_text_not_in_sources": (
        "초안·입력·근거나 요청에 없는 글자가 들어갔습니다 — 바꿀 글자를 따옴표로 적어 주십시오."
    ),
    "figure_number_not_in_sources": (
        "근거에 없는 수치가 들어갔습니다 — 수치는 초안·입력에 있는 것만 씁니다."
    ),
    "figure_fact_not_found": "수치 그래프 값은 출처 문서의 검증 수치만 씁니다.",
    "figure_schedule_exceeds_period": "일정이 연구기간을 넘습니다.",
    "figure_box_empty": "개념도 상자마다 한 줄 이상 남아 있어야 합니다.",
    "schema": "그림 형식(상자·단계 개수, 글자 길이)에 맞지 않습니다.",
    "json": "모델 답을 읽지 못했습니다 — 다시 시도해 주십시오.",
    "no_change": "요청에서 바꿀 점을 찾지 못했습니다 — 무엇을 어떻게 바꿀지 적어 주십시오.",
    "internal_text": "공용 계정에서는 사내 자료에만 있는 글자를 그림에 넣을 수 없습니다.",
    "budget": "오늘 그림 호출 상한에 이르렀습니다.",
}


_TECHNIQUE_REJECT = {
    "skip": "이 제안 내용으로는 이 기법의 의미 있는 분석이 나오지 않습니다 (해당 없음).",
    "json": "모델 답을 읽지 못했습니다 — 다시 시도해 주십시오 (호출 실패).",
    "schema": "분석 결과가 기법 형식에 맞지 않았습니다 — 다시 시도해 주십시오 (규칙에 걸러짐).",
    "internal_text": "공용 계정에서는 사내 자료에만 있는 글자를 그림에 넣을 수 없습니다.",
}


def _technique_reject(code: str | None) -> str:
    """[11] 기법 분석 실패 → 안내 한 문장 (사유: 호출 실패·해당 없음·규칙에 걸러짐)."""
    code = code or "invalid"
    if code in _TECHNIQUE_REJECT:
        return _TECHNIQUE_REJECT[code]
    if code.startswith("technique_") or code.startswith("figure_"):
        return (
            "분석 결과가 출처·형식 검사를 통과하지 못했습니다 — 다른 기법을 고르거나 "
            "다시 시도해 주십시오 (규칙에 걸러짐)."
        )
    return "분석 기법 호출이 실패했습니다 — 잠시 뒤 다시 시도해 주십시오 (호출 실패)."


def _edit_reject_hint(code: str) -> str:
    """[말로 고치기] 거절 사유 코드 → 안내 한 문장 (앱 문구, 원문 없음)."""
    return _EDIT_REJECT_HINTS.get(code, "")


def _figure_summary(figures: list[Figure], previous: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """RunState.figures(manifest 용) — 배치(placement)는 마무리 때 적히므로 이전 값을 이어받는다."""
    prev = {str(p.get("id")): p for p in previous}
    out = []
    for f in figures:
        row = {
            "id": f.id,
            "kind": f.kind,
            "section": f.section,
            "renderer": f.renderer,
            "model": f.model,
            "calls": f.calls,
            "included": f.included,
            "confirmed": f.confirmed,
            "error": f.error,
            "placement": prev.get(f.id, {}).get("placement"),
            "number": prev.get(f.id, {}).get("number"),
        }
        out.append(row)
    return out


def figure_rules_changed(old: list[Figure], new: list[Figure]) -> list[Figure]:
    changed_ids = {row["figure_id"] for row in figure_rules.figure_diff(old, new)}
    return [f for f in new if f.id in changed_ids] or [f for f in old if f.id in changed_ids]


# ── [5] 순수 함수 ─────────────────────────────────────────
def _evidence_url(doc: Any, raw: Mapping[str, Any], basis: str | None) -> str | None:
    """근거 원본 링크 — 이미지 판독은 raw.image.url(없으면 페이지 url), 그 밖은 문서 url."""
    image = raw.get("image") if isinstance(raw, Mapping) else None
    if basis == "image_vision" and isinstance(image, Mapping):
        link = image.get("url") or image.get("page_url")
        if isinstance(link, str) and link:
            return link
    link = getattr(doc, "url", None) if doc is not None else None
    return link if isinstance(link, str) and link else None


def _auto_fixed(old: list[Section], new: list[Section]) -> int:
    """Q6 규칙 검사가 바꾼 문장 수 — 자리별 텍스트 차이 + 줄어든(중복 제거) 개수."""
    total = 0
    for a, b in zip(old, new, strict=False):
        ta, tb = [s.text for s in a.sentences], [s.text for s in b.sentences]
        total += abs(len(ta) - len(tb)) + sum(1 for x, y in zip(ta, tb, strict=False) if x != y)
    return total


def _review_key(run_id: str, round_no: int) -> str:
    return f"{run_id}:review:{round_no}"


def changed_sentence_ids(old: DraftVersion, new: DraftVersion) -> set[str]:
    """두 버전 사이에 텍스트가 바뀐(추가·삭제 포함) 문장 id."""
    out: set[str] = set()
    for sec in new.sections:
        before = old.section(sec.key)
        old_texts = [s.text for s in before.sentences] if before else []
        for i, s in enumerate(sec.sentences):
            if i >= len(old_texts) or old_texts[i] != s.text:
                out.add(sentence_id(sec.key, i))
        for i in range(len(sec.sentences), len(old_texts)):
            out.add(sentence_id(sec.key, i))
    return out


def apply_edit_request(
    sections: list[Section], edits: EditRequest, review: ReviewRound | None
) -> tuple[list[Section], set[str]]:
    """편집 요청을 섹션 목록에 적용한 새 목록과, 채택된 의견 id.

    - use_revision: 최신 차수의 검증 통과(usable) 수정안만. 근거는 수정안의 evidence(비면 원문),
      origin=reviewed.
    - manual: 텍스트만 바꾸고 원래 근거 id 유지, origin=proposer_edit. 버리지 않는다.
    - delete: 문장 삭제. insert_after: 그 문장 뒤에 새 문장(origin=proposer_input, 근거 없음).
    - 섹션 전체 편집(texts 또는 text): 같은 문장은 근거·출처를 이어받고 새 문장은 proposer_input.
      order 는 재배열.
    같은 섹션 안의 문장 편집은 인덱스가 밀리지 않도록 삭제·삽입을 뒤 문장부터 적용한다.
    선택값(choices)은 바꾸지 않는다.
    """
    by_key = {s.key: s for s in sections}
    used: set[str] = set()
    parsed_edits: list[tuple[str, int, Any]] = []
    for edit in edits.sentences:
        parsed = parse_sentence_id(edit.sentence_id)
        if parsed is None:
            raise EditRejected(f"문장 id 형식이 올바르지 않습니다: {edit.sentence_id}")
        key, idx = parsed
        sec = by_key.get(key)
        if sec is None or idx >= len(sec.sentences):
            raise EditRejected(f"그런 문장이 없습니다: {edit.sentence_id}")
        parsed_edits.append((key, idx, edit))
    # 치환은 순서 무관, 삭제·삽입은 인덱스가 큰 것부터
    for key, idx, edit in sorted(parsed_edits, key=lambda x: -x[1]):
        sec = by_key[key]
        original = sec.sentences[idx]
        sentences = list(sec.sentences)
        if edit.action == "keep":
            continue
        if edit.action == "delete":
            del sentences[idx]
        elif edit.action == "insert_after":
            text = clean_sentence(edit.text or "")
            if not text:
                raise EditRejected(f"{edit.sentence_id}: 추가할 문장이 비어 있습니다.")
            sentences.insert(idx + 1, Sentence(text=text, evidence=[], origin="proposer_input"))
        elif edit.action == "manual":
            text = clean_sentence(edit.text or "")
            if not text:
                raise EditRejected(f"{edit.sentence_id}: 직접 수정 문장이 비어 있습니다.")
            sentences[idx] = Sentence(
                text=text, evidence=list(original.evidence), origin="proposer_edit"
            )
        else:  # use_revision
            comment = _pick_revision(review, key, idx, edit.comment_id)
            if comment is None:
                raise EditRejected(
                    f"{edit.sentence_id}: 사용할 수 있는 수정안이 없습니다 (검증 통과분만)."
                )
            sentences[idx] = Sentence(
                text=comment.revised_text or original.text,
                evidence=list(comment.evidence or original.evidence),
                origin="reviewed",
            )
            used.add(comment.id)
        by_key[key] = sec.model_copy(update={"sentences": sentences})
    for edit in edits.sections:
        sec = by_key.get(edit.section)
        if sec is None:
            raise EditRejected(f"그런 섹션이 없습니다: {edit.section}")
        if edit.order is not None:
            try:
                sec = reorder(sec, edit.order)
            except ValueError as exc:
                raise EditRejected(str(exc)) from exc
        texts = list(edit.texts)
        if edit.text is not None:
            texts = split_sentences(edit.text)
        if edit.texts or edit.text is not None:
            sec = section_from_texts(sec, texts)
        by_key[edit.section] = sec
    return [by_key[s.key] for s in sections], used


def _annotations_from(review: ReviewRound, applied: list[str]) -> list[Annotation]:
    """수정안 없이 의견만 있는 항목·폐기된 수정안·섹션 의견 → 문장 메모 (v2 에 붙는다)."""
    out: list[Annotation] = []
    for c in review.comments:
        if c.id in applied:
            continue
        if c.discard_reason == "candidate_replaced":
            continue  # 버린 후보(A)의 문장에 대한 의견 — v2 에는 그 문장이 없다
        if c.status == "discarded":
            kind = "discarded"
        elif c.sentence is None:
            kind = "section"
        else:
            kind = "opinion"
        text = c.comment
        if c.status == "discarded" and c.revised_text:
            text = f"{c.comment} (폐기된 수정안: {c.revised_text})"
        out.append(
            Annotation(
                id=c.id,
                section=c.section,
                sentence=c.sentence,
                kind=kind,
                text=text[:2000],
                reason=c.discard_reason,
            )
        )
    return out


def _pick_revision(
    review: ReviewRound | None, key: str, idx: int, comment_id: str | None
) -> ReviewComment | None:
    if review is None:
        return None
    for c in review.comments:
        if comment_id is not None and c.id != comment_id:
            continue
        if c.section == key and c.sentence == idx and c.usable:
            return c
    return None
