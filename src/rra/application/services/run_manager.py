"""생성 실행 관리자 — 상태 저장, 중단 후 재개, 단계별 진행 기록, 동시성 1.

모든 진입점(CLI·MCP, 이후 REST)이 이 클래스로만 생성한다.

- 재개 단위는 step: retrieve(1회, 스냅샷 저장) → section:<key>(LLM 1회씩) → finalize(lint).
  이미 저장된 step 은 건너뛴다. 검색은 재개 때 다시 하지 않는다 (근거 집합 고정).
- 섹션은 근거 검증을 통과한 뒤에만 저장된다 → 부분 초안도 항상 인용 규칙을 만족한다.
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
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from rra.application.ports import (
    GenerationSlot,
    RunBusy,
    RunClaim,
    RunLogPort,
    RunNotFound,
    RunStorePort,
)
from rra.application.usecases.generate_proposal import GenerateProposal
from rra.domain.models import (
    Confirmation,
    ProposalRequest,
    RetrievalSnapshot,
    RunState,
    Section,
    StepRecord,
)
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
from rra.domain.rules.lint import has_errors

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


class ConfirmRejected(ValueError):
    """선택값 확정 요청이 규칙(선택지 목록·개수·run 상태)에 맞지 않는다."""


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


def _utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class RunManager:
    def __init__(
        self,
        generate: GenerateProposal,
        store: RunStorePort,
        slot: GenerationSlot,
        run_log: RunLogPort,
        *,
        max_queued: int = 3,
        model: str | None = None,
        clock: Callable[[], str] = _utcnow,
    ):
        self.generate = generate
        self.store = store
        self.slot = slot
        self.run_log = run_log
        self.max_queued = max_queued
        self.model = model
        self._clock = clock
        self._tasks: dict[str, asyncio.Task[RunState]] = {}

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
        """같은 프로세스에서 시작한 run 이 끝날 때까지 기다린다 (CLI 용)."""
        task = self._tasks.get(run_id)
        if task is not None:
            return await task
        return await self.status(user, run_id)

    def _start(self, state: RunState, claim: RunClaim, on_step: StepCallback | None) -> None:
        task = asyncio.create_task(self._execute(state.user, state.run_id, claim, on_step))
        self._tasks[state.run_id] = task
        task.add_done_callback(lambda _t, rid=state.run_id: self._tasks.pop(rid, None))

    # ── 실행 ─────────────────────────────────────────────
    async def _execute(
        self, user: str, run_id: str, claim: RunClaim, on_step: StepCallback | None
    ) -> RunState:
        state = self.store.load_state(user, run_id)
        current: StepRecord | None = None
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
                    snapshot = self.generate.retrieve(req)
                    self.store.save_snapshot(user, run_id, snapshot)
                    self._finish(state, current, on_step, evidence=sorted(snapshot.retrieved_ids))
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
                    )
                    current = None

                current = self._begin(state, FINALIZE)
                ordered = [sections[k] for k in self.generate.section_keys]
                draft, problems = self.generate.finalize(run_id, req, snapshot, ordered)
                self.store.save_draft(user, run_id, draft)
                state.problems = [p.model_dump() for p in problems]
                state.status = "invalid" if has_errors(problems) else "done"
                self._finish(state, current, on_step)
                current = None
                return state
        except asyncio.CancelledError:
            self._interrupt(state, current, "CancelledError")
            raise
        except Exception as exc:  # 어떤 실패든 저장된 step 은 남고, 재개로 이어서 한다
            self._interrupt(state, current, type(exc).__name__)
            logger.warning("run.interrupted run=%s error=%s", run_id, type(exc).__name__)
            return state
        finally:
            state.updated_at = self._clock()
            self._save(state)
            claim.release()

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
        self.run_log.record(
            state.run_id,
            manifest(
                state,
                self.store.load_snapshot(state.user, state.run_id),
                self.store.load_confirmation(state.user, state.run_id),
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
        if state.status in ACTIVE and state.run_id not in self._tasks:
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
        # 순서는 run 이 계획한 순서 — 양식이 바뀌어도 예전 run 은 자기 섹션으로 보인다
        sections = [stored[k] for k in state.section_keys if k in stored]
        snapshot = self.store.load_snapshot(user, run_id)
        legacy = self.is_legacy(state)
        return DraftView(
            state=state,
            sections=sections,
            citations=self._citations(sections, snapshot),
            legacy=legacy,
            confirmation=self.store.load_confirmation(user, run_id),
            choice_options={} if legacy else self.generate.choice_options(),
        )

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

    def _citations(
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
            doc = self.generate.repo.get_document(doc_of[ev])
            out.append(Citation(id=ev, doc_id=doc_of[ev], title=doc.title if doc else None))
        return out


def manifest(
    state: RunState,
    snapshot: RetrievalSnapshot | None,
    confirmation: Confirmation | None = None,
) -> dict[str, Any]:
    """보안 I: 해시·id·개수·클래스명만. 입력·문장·lint 메시지(문장 앞부분 포함)는 제외."""
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
    }
