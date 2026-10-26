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

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
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
from rra.application.ports.renderer import RenderRejected
from rra.application.usecases.generate_proposal import GenerateProposal
from rra.application.usecases.render_check import RenderCheck, render_check
from rra.application.usecases.review_draft import ReviewContext, ReviewDraft
from rra.domain.models import (
    Confirmation,
    Draft,
    DraftVersion,
    ProposalRequest,
    ProposerInfo,
    RetrievalSnapshot,
    ReviewComment,
    ReviewRound,
    RunState,
    Section,
    Sentence,
    StepRecord,
)
from rra.domain.models.review import EditRequest, parse_sentence_id, sentence_id
from rra.domain.models.run import (
    ACTIVE,
    FINALIZE,
    FINISHED,
    RESUMABLE,
    RETRIEVE,
    is_valid_run_id,
    plan_steps,
    section_step,
)
from rra.domain.rules import review_flow
from rra.domain.rules.lint import has_errors, lint
from rra.domain.rules.llm_output import clean_sentence
from rra.domain.rules.review_flow import InvalidTransition

logger = logging.getLogger("rra.runs")

StepCallback = Callable[[RunState, StepRecord], None]

__all__ = [
    "Citation",
    "ConfirmRejected",
    "DraftView",
    "QueueFull",
    "RunBusy",
    "RunManager",
    "RunNotFound",
    "RunNotResumable",
]


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
    """최종 마무리 조건(검토 1회 이상 또는 건너뜀, 검토 중 아님)에 맞지 않는다."""


@dataclass(frozen=True)
class FinalizeResult:
    data: bytes  # HWPX
    confirmation: Confirmation
    check: RenderCheck
    version: int
    state: RunState


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
    ):
        self.generate = generate
        self.reviewer = reviewer  # None 이면 검토를 건너뛴다 (review_skipped)
        self.review_auto = review_auto
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
        self, user: str, req: ProposalRequest, *, on_step: StepCallback | None = None
    ) -> RunState:
        """queued 로 저장하고 백그라운드 실행을 시작한 뒤 즉시 돌려준다."""
        active = [s for s in self.list_runs(user) if s.status in ACTIVE]
        if len(active) >= self.max_queued:
            raise QueueFull(
                f"대기·실행 중인 생성이 {len(active)}건입니다 (상한 {self.max_queued})."
            )
        state = self.store.create(user, req, plan_steps(self.generate.section_keys), self._clock())
        state.model = self.model
        state.template = self.generate.template
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
        try:
            async with self.slot.acquire():
                state.status = "running"
                self._save(state)
                try:
                    req = self.store.load_request(user, run_id)
                except ValidationError:
                    state.status = "failed"  # 저장된 입력이 깨짐 — 재개해도 소용없다
                    return state

                snapshot = self.store.load_snapshot(user, run_id)
                if snapshot is None:
                    current = self._begin(state, RETRIEVE)
                    snapshot = await self.generate.retrieve(req)
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

                sections = self.store.load_sections(user, run_id)
                for key in self.generate.section_keys:
                    if key in sections:
                        self._ensure_done(state, section_step(key))
                        continue
                    current = self._begin(state, section_step(key))
                    composed = await self.generate.compose_section(key, req, snapshot)
                    self.store.save_section(user, run_id, composed.section)
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
                    self._finish(
                        state,
                        current,
                        on_step,
                        sentences=len(composed.section.sentences),
                        dropped=len(composed.dropped),
                        evidence=sorted(
                            {e for s in composed.section.sentences for e in s.evidence}
                        ),
                        prompt_hash=composed.prompt_hash,
                        parse=parse.status if parse is not None else composed.mode,
                        raw_chars=parse.raw_chars if parse is not None else None,
                        retries=composed.retries,
                    )
                    current = None

                current = self._begin(state, FINALIZE)
                ordered = [sections[k] for k in self.generate.section_keys]
                draft, problems = self.generate.finalize(run_id, req, snapshot, ordered)
                self.store.save_draft(user, run_id, draft)
                state.problems = [p.model_dump() for p in problems]
                state.status = "invalid" if has_errors(problems) else "done"
                if state.status == "done":  # draft_v1 = 로컬 초안
                    self.store.save_version(
                        user,
                        run_id,
                        DraftVersion(
                            version=1, origin="local", sections=ordered, created_at=self._clock()
                        ),
                    )
                    state.draft_version = 1
                    if self.review_auto and self.reviewer is None:
                        self._skip_review(user, run_id, state)  # review_skipped, 상태는 done
                    auto_review = self.review_auto and self.reviewer is not None
                self._finish(state, current, on_step)
                current = None
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
            if auto_review:  # 초안 완료 뒤 1차 검토 자동 시작 (review.auto). 락을 놓은 뒤에
                try:
                    await self.review(user, run_id)
                except (QueueFull, RunBusy, InvalidTransition) as exc:
                    logger.warning(
                        "run.auto_review_skipped run=%s reason=%s", run_id, type(exc).__name__
                    )

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
        self.run_log.record(
            state.run_id,
            manifest(
                state,
                self.store.load_snapshot(state.user, state.run_id),
                self.store.load_confirmation(state.user, state.run_id),
                reviews,
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

    def _normalize(self, state: RunState) -> RunState:
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
        return DraftView(
            state=state,
            sections=sections,
            citations=await self._citations(sections, snapshot),
            legacy=legacy,
            confirmation=self.store.load_confirmation(user, run_id),
            choice_options={} if legacy else self.generate.choice_options(),
            version=max(state.draft_version, 1),
            versions=self.store.list_versions(user, run_id),
            review=self.store.load_review(user, run_id, reviews[-1]) if reviews else None,
            reviews=reviews,
        )

    # ── [5] 검토 ─────────────────────────────────────────
    async def review(self, user: str, run_id: str) -> RunState:
        """검토(n차)를 시작한다. 검토 LLM 이 없으면 건너뛰고 review_skipped 를 기록한다.

        동시성 1·대기열 3(QueueFull)은 생성과 같은 슬롯·상한을 쓴다. 백그라운드로 돌고 상태만
        돌려준다.
        """
        state = await self.status(user, run_id)
        if self.is_legacy(state):
            raise InvalidTransition(LEGACY_HINT.format(run_id=run_id))
        if self.reviewer is None:  # 검토 LLM 없음 → 건너뜀 기록, 상태는 그대로 (finalize 가능)
            if not review_flow.can_review(state.status):
                raise InvalidTransition(review_flow.hint(state.status, "start_review"))
            self._skip_review(user, run_id, state)
            self._save(state)
            return state
        nxt = review_flow.transition(state.status, "start_review")  # 불가면 InvalidTransition
        active = [s for s in self.list_runs(user) if s.status in ACTIVE]
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
        self.runner.submit(key, self._execute_review(user, run_id, claim))
        return state

    def _skip_review(self, user: str, run_id: str, state: RunState) -> None:
        state.review_skipped = True
        self.store.save_review(
            user,
            run_id,
            ReviewRound(
                round=len(self.store.list_reviews(user, run_id)) + 1,
                draft_version=max(state.draft_version, 1),
                status="skipped",
                skipped_reason="no_review_llm",
                created_at=self._clock(),
            ),
        )

    async def _execute_review(self, user: str, run_id: str, claim: RunClaim) -> RunState:
        state = self.store.load_state(user, run_id)
        reviewer = self.reviewer
        if reviewer is None:  # review() 가 막지만 방어
            raise RuntimeError("reviewer missing")
        try:
            async with self.slot.acquire():
                version = self._current_version(user, run_id, state)
                snapshot = self.store.load_snapshot(user, run_id)
                if snapshot is None:
                    raise RuntimeError("retrieval snapshot missing")
                rounds = self.store.list_reviews(user, run_id)
                previous = self.store.load_review(user, run_id, rounds[-1]) if rounds else None
                changed = self._changed_since(user, run_id, version, previous)
                result = await reviewer(
                    ReviewContext(
                        run_id=run_id,
                        round_no=len(rounds) + 1,
                        version=version,
                        snapshot=snapshot,
                        request=self.store.load_request(user, run_id),
                        previous=previous if previous and previous.status == "done" else None,
                        changed=changed,
                        confirmation=self.store.load_confirmation(user, run_id),
                    )
                )
                result = result.model_copy(update={"created_at": self._clock()})
                self.store.save_review(user, run_id, result)
                self._mark_resolved(user, run_id, previous, result.resolved_ids)
                state.review_rounds += 1
                state.review_model = (
                    f"{reviewer.provider}/{reviewer.model}"
                    if reviewer.provider or reviewer.model
                    else None
                )
                state.status = review_flow.transition(state.status, "finish_review")
                state.review_from = None
                return state
        except Exception as exc:  # 검토 실패 — 검토 전 상태로 돌아간다 (초안은 그대로)
            state.status = review_flow.transition(
                "reviewing", "fail_review", previous=state.review_from
            )
            state.review_error = type(exc).__name__
            state.review_from = None
            logger.warning("run.review_failed run=%s error=%s", run_id, type(exc).__name__)
            return state
        finally:
            self._save(state)
            claim.release()

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
        old = self.store.load_version(user, run_id, previous.draft_version)
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

    # ── [5] 버전·편집·되돌리기 ───────────────────────────
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
        self, user: str, run_id: str, round_no: int | None = None
    ) -> ReviewRound | None:
        """검토 결과 — round_no 가 없으면 최신 차수. 없으면 None."""
        await self.status(user, run_id)
        rounds = self.store.list_reviews(user, run_id)
        if not rounds:
            return None
        if round_no is None:
            round_no = rounds[-1]
        return self.store.load_review(user, run_id, round_no) if round_no >= 1 else None

    async def get_version(self, user: str, run_id: str, version: int) -> DraftVersion:
        await self.status(user, run_id)
        found = self.store.load_version(user, run_id, version) if version >= 1 else None
        if found is None:
            raise EditRejected(f"버전 v{version} 이 없습니다.")
        return found

    async def apply_edits(self, user: str, run_id: str, edits: EditRequest) -> DraftVersion:
        """제안자 편집 반영 → 새 버전. 수정안 사용은 5-4 통과분만, 직접 수정은 "제안자 수정".

        lint 는 돌려 알림(state.problems)만 남긴다 — 제안자 수정 문장은 버리지 않는다.
        """
        state = await self.status(user, run_id)
        if self.is_legacy(state):
            raise EditRejected(LEGACY_HINT.format(run_id=run_id))
        try:
            nxt = review_flow.transition(state.status, "edit")
        except InvalidTransition as exc:
            raise EditRejected(str(exc)) from exc
        if not edits.sentences and not edits.sections:
            raise EditRejected("반영할 편집이 없습니다.")
        current = self._current_version(user, run_id, state)
        rounds = self.store.list_reviews(user, run_id)
        latest = self.store.load_review(user, run_id, rounds[-1]) if rounds else None
        sections, used = apply_edit_request(current.sections, edits, latest)
        new_version = DraftVersion(
            version=current.version + 1,
            origin="edit",
            sections=sections,
            created_at=self._clock(),
            based_on_review=latest.round if latest else None,
            note=edits.note,
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
        return new_version

    async def revert(self, user: str, run_id: str, to: int) -> DraftVersion:
        """이전 버전 내용으로 새 버전을 만든다 (기록은 지우지 않는다)."""
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
            note=f"v{to} 로 되돌림",
        )
        self._store_version(user, run_id, state, new_version, nxt)
        return new_version

    def _store_version(
        self, user: str, run_id: str, state: RunState, version: DraftVersion, status: str
    ) -> None:
        self.store.save_version(user, run_id, version)
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
        chunk_texts = {c.chunk_id: c.text for c in snapshot.chunks} if snapshot else {}
        problems = lint(
            draft,
            self.generate.rules,
            choice_options=self.generate.choice_options(),
            chunk_texts=chunk_texts,
            evidence_skipped=self.generate.evidence_skipped(snapshot) if snapshot else None,
        )
        state.problems = [
            p.model_dump() for p in problems
        ]  # 알림만 — 상태를 invalid 로 바꾸지 않는다
        state.draft_version = version.version
        state.status = status
        self._save(state)

    # ── [5] 최종 마무리·다시 열기 ───────────────────────
    async def finalize(
        self,
        user: str,
        run_id: str,
        *,
        choices: Mapping[str, list[str]] | None = None,
        proposer: ProposerInfo | None = None,
    ) -> FinalizeResult:
        """선택형 확정(제안값이 기본) + 제안자 정보 + render_check → finalized → HWPX.

        제안자 정보·제안부서·제안일자는 렌더 인자로만 쓰고 저장하지 않는다. 다시 마무리하면 새 파일.
        """
        if self.renderer is None:
            raise RenderUnavailable("렌더러가 설정되지 않았습니다 (uv pip install -e '.[render]').")
        state = await self.status(user, run_id)
        if self.is_legacy(state):
            raise FinalizeRejected(LEGACY_HINT.format(run_id=run_id))
        if not review_flow.can_finalize(
            state.status, review_rounds=state.review_rounds, review_skipped=state.review_skipped
        ):
            raise FinalizeRejected(
                f"{state.status} 상태에서는 마무리할 수 없습니다 — 검토 1회 이상(또는 건너뜀) 뒤, "
                "검토 중이 아닐 때만."
            )
        view = await self.get_draft(user, run_id)
        confirmation = await self._confirm_for_finalize(user, run_id, view, choices)
        check = await self.render_check(user, run_id, proposer=proposer)
        draft = Draft(
            run_id=run_id,
            request=self.store.load_request(user, run_id),
            sections=view.sections,
            template=state.template,
        )
        data = self.renderer.render(draft, confirmation=confirmation, proposer=proposer)
        state = await self.status(user, run_id)
        state.status = review_flow.transition(state.status, "finalize")
        state.finalized_at = self._clock()
        self._save(state)
        return FinalizeResult(
            data=data, confirmation=confirmation, check=check, version=view.version, state=state
        )

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
) -> dict[str, Any]:
    """보안 I: 해시·id·개수·클래스명만. 입력·문장·lint 메시지(문장 앞부분 포함)·의견 원문은 제외.

    검토는 차수별 provider·model, 외부 전송 doc_id(public/internal 구분), 보낸 문장 수만 남긴다.
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
                }
                for r in reviews or []
            ],
        },
        "finalized_at": state.finalized_at,
    }


# ── [5] 순수 함수 ─────────────────────────────────────────
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

    - use_revision: 최신 차수의 검증 통과(usable) 수정안만. 근거는 수정안의 evidence(비면 원문).
    - manual: 텍스트만 바꾸고 원래 근거 id 유지, origin="proposer" ("제안자 수정"). 버리지 않는다.
    - 섹션 전체 편집: 문장 목록을 통째로 교체, 같은 자리의 원래 근거는 유지.
    """
    by_key = {s.key: s for s in sections}
    used: set[str] = set()
    for edit in edits.sentences:
        parsed = parse_sentence_id(edit.sentence_id)
        if parsed is None:
            raise EditRejected(f"문장 id 형식이 올바르지 않습니다: {edit.sentence_id}")
        key, idx = parsed
        sec = by_key.get(key)
        if sec is None or idx >= len(sec.sentences):
            raise EditRejected(f"그런 문장이 없습니다: {edit.sentence_id}")
        original = sec.sentences[idx]
        if edit.action == "keep":
            continue
        if edit.action == "manual":
            text = clean_sentence(edit.text or "")
            if not text:
                raise EditRejected(f"{edit.sentence_id}: 직접 수정 문장이 비어 있습니다.")
            new_sentence = Sentence(text=text, evidence=list(original.evidence), origin="proposer")
        else:  # use_revision
            comment = _pick_revision(review, key, idx, edit.comment_id)
            if comment is None:
                raise EditRejected(
                    f"{edit.sentence_id}: 사용할 수 있는 수정안이 없습니다 (검증 통과분만)."
                )
            new_sentence = Sentence(
                text=comment.revised_text or original.text,
                evidence=list(comment.evidence or original.evidence),
                origin="reviewed",
            )
            used.add(comment.id)
        sentences = list(sec.sentences)
        sentences[idx] = new_sentence
        by_key[key] = sec.model_copy(update={"sentences": sentences})
    for edit in edits.sections:
        sec = by_key.get(edit.section)
        if sec is None:
            raise EditRejected(f"그런 섹션이 없습니다: {edit.section}")
        texts = [clean_sentence(t) for t in edit.texts if clean_sentence(t)]
        sentences = [
            Sentence(
                text=t,
                evidence=list(sec.sentences[i].evidence) if i < len(sec.sentences) else [],
                origin="proposer",
            )
            for i, t in enumerate(texts)
        ]
        by_key[edit.section] = sec.model_copy(update={"sentences": sentences})
    return [by_key[s.key] for s in sections], used


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
