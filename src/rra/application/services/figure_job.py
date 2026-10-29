"""그림 백그라운드 작업(ADR 0045) — 초안 글을 먼저 보이고(drafted) 그림은 뒤에서 그린다.

- 시작: 생성 실행(_execute)이 v1 을 저장하고 drafted 로 바꾸기 직전에 그림 작업 락(.figures.lock)을
  잡고 작업 파일(figures_job.json, 자리 목록)을 쓴다. run 락을 놓은 뒤 TaskRunner 로 띄운다
  (key "<run_id>:figures"). run 락·생성 칸(run_slot)·전역 슬롯은 잡지 않는다 —
  편집은 그대로 열린다.
  명세의 로컬 대체만 그림 유스케이스가 전역 슬롯을 잡는다(local_held=False).
- 도착: 그림 한 장이 끝날 때마다 작업 파일에 넣는다(동기 구간, await 없음).
  버전 파일은 그대로 — 읽기(_version)가 작업 그림을 합친다. 그동안 제안자가 v2·v3 을
  저장해도 그림 때문에 내용 버전이 생기지 않고 제안자의 편집도 그대로다.
- 끝: 그동안 만든 버전 파일(base_version 이상)에 그림을 한 번 채운다
  (버전에 이미 있는 그림이 이긴다).
- 재시작: 작업이 사라졌으면(같은 프로세스에 작업이 없고 락도 풀림) 읽을 때 failed 로 —
  그리던 자리는 실패 카드([다시 그리기])로 남고 "그리는 중" 이 영원히 남지 않는다.
- 상태 파일이 아니라 작업 파일에 두는 이유: 다른 동작이 들고 있던 옛 RunState 를
  저장해도 그림 진행이 되돌아가지 않게. 읽을 때(_overlay_figure_job) RunState 의
  figures_status·figure_slots·두 시간에 채운다.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from rra.application.ports import RunClaim
from rra.domain.models import DraftVersion, FigureJob
from rra.domain.models.run import FIGURES
from rra.domain.rules import figure_job as job_rules
from rra.domain.rules import figures as figure_rules

if TYPE_CHECKING:  # pragma: no cover
    from rra.application.usecases.figures import FigureBuild
    from rra.domain.models import ProposalRequest, RetrievalSnapshot, RunState, Section

logger = logging.getLogger("rra.runs")


def figure_key(run_id: str) -> str:
    """TaskRunner key — 생성(run_id)·검토(run_id:review:n)와 겹치지 않는다."""
    return f"{run_id}:figures"


class FigureJobMixin:
    """RunManager 전용 — self.store·runner·figures·_clock·_save·_touch_usage·review 를 쓴다."""

    # ── 읽기 ─────────────────────────────────────────────
    def _figure_job(self, user: str, run_id: str) -> FigureJob | None:
        loader = getattr(self.store, "load_figure_job", None)  # type: ignore[attr-defined]
        return loader(user, run_id) if loader is not None else None

    def _merge_job_figures(self, user: str, run_id: str, version: DraftVersion) -> DraftVersion:
        """버전 + 아직 버전 파일에 채우지 않은 작업 그림 (그리는 중·끝났지만 채우기 전)."""
        job = self._figure_job(user, run_id)
        if job is None or job.applied or not job.figures or version.version < job.base_version:
            return version
        merged = job_rules.merge_figures(version.figures, job.figures)
        if len(merged) == len(version.figures):
            return version
        return version.model_copy(update={"figures": merged})

    def _figures_busy(self, user: str, run_id: str) -> bool:
        job = self._figure_job(user, run_id)
        return job is not None and job.status in job_rules.ACTIVE_JOB

    def _overlay_figure_job(self, state: RunState) -> RunState:
        """작업 파일 → RunState 의 figures_status·figure_slots·시간. 작업이 사라졌으면 failed 로."""
        job = self._figure_job(state.user, state.run_id)
        if job is None:
            return state
        if (
            job.status in job_rules.ACTIVE_JOB
            and not self.runner.is_running(figure_key(state.run_id))  # type: ignore[attr-defined]
            and not self.store.figures_alive(state.user, state.run_id)  # type: ignore[attr-defined]
        ):
            job = job_rules.interrupt(job, self._clock())  # type: ignore[attr-defined]
            self.store.save_figure_job(state.user, state.run_id, job)  # type: ignore[attr-defined]
            job = self._apply_job_to_versions(state.user, state.run_id, job)
            self._figure_step_status(state, job)
            logger.warning("figure.job_interrupted run=%s", state.run_id)
            self._fill_from_job(state, job)
            self._save(state)  # type: ignore[attr-defined]
            return state
        self._fill_from_job(state, job)
        return state

    def _fill_from_job(self, state: RunState, job: FigureJob) -> None:
        state.figures_status = job.status
        state.figure_slots = [
            {**s.model_dump(), "reason_label": job_rules.reason_label(s.reason, s.status)}
            for s in job_rules.open_slots(job)
        ]
        if job.draft_visible_seconds is not None:
            state.draft_visible_seconds = job.draft_visible_seconds
        state.figures_done_seconds = job.figures_done_seconds
        if job.status not in job_rules.ACTIVE_JOB:
            self._figure_step_status(state, job)  # 옛 상태를 저장한 동작이 있어도 단계는 작업 기준
            return
        try:
            step = state.step(FIGURES)
        except KeyError:
            return
        step.status, step.error = "pending", None

    # ── 시작 ─────────────────────────────────────────────
    def _prepare_figure_job(
        self,
        user: str,
        run_id: str,
        state: RunState,
        sections: list[Section],
        req: ProposalRequest,
        snapshot: RetrievalSnapshot | None,
    ) -> RunClaim | None:
        """v1 저장 뒤·drafted 전 — 그림 작업 락을 잡고 자리 목록을 쓴다. 그림 단계가 없으면 None."""
        figures = getattr(self, "figures", None)
        if figures is None or not any(s.name == FIGURES for s in state.steps):
            return None
        try:
            claim = self.store.claim_figures(user, run_id)  # type: ignore[attr-defined]
        except Exception as exc:  # 다른 프로세스가 이미 그리고 있다 — 그 작업에 맡긴다
            logger.warning("figure.job_busy run=%s error=%s", run_id, type(exc).__name__)
            return None
        try:
            want = figures.config.max_default
            plan = figures.plan(sections, req, snapshot, all_candidates=True)[:want]
            tech = figure_rules.technique_slots(len(figures.plan(sections, req, snapshot))) > 0
        except Exception as exc:  # 계획 실패 — 그림 없이 초안만
            claim.release()
            logger.warning("figure.plan_failed run=%s error=%s", run_id, type(exc).__name__)
            return None
        now = self._clock()  # type: ignore[attr-defined]
        job = job_rules.new_job(
            plan,
            technique_slot=tech,
            base_version=max(state.draft_version, 1),
            now=now,
            submitted_at=state.created_at,
        )
        self.store.save_figure_job(user, run_id, job)  # type: ignore[attr-defined]
        step = state.step(FIGURES)
        step.status, step.error, step.started_at, step.finished_at = "pending", None, now, None
        self._fill_from_job(state, job)
        return claim

    def _start_figure_job(self, user: str, run_id: str, claim: RunClaim) -> None:
        try:
            self.runner.submit(  # type: ignore[attr-defined]
                figure_key(run_id), self._execute_figures(user, run_id, claim)
            )
        except Exception as exc:  # 이미 같은 작업이 돌고 있다 — 락만 놓는다
            claim.release()
            logger.warning("figure.job_submit_failed run=%s error=%s", run_id, type(exc).__name__)

    # ── 실행 ─────────────────────────────────────────────
    def _update_job(
        self, user: str, run_id: str, change: Callable[[FigureJob], FigureJob]
    ) -> FigureJob | None:
        """작업 파일 읽기 → 바꾸기 → 쓰기.
        await 없는 동기 구간이라 같은 프로세스의 다른 작업이 끼어들 수 없다."""
        job = self._figure_job(user, run_id)
        if job is None:
            return None
        job = change(job)
        self.store.save_figure_job(user, run_id, job)  # type: ignore[attr-defined]
        return job

    def _taken_ids(self, user: str, run_id: str) -> list[str]:
        state = self.store.load_state(user, run_id)  # type: ignore[attr-defined]
        current = self._version(user, run_id, max(state.draft_version, 1))  # type: ignore[attr-defined]
        job = self._figure_job(user, run_id)
        return sorted(
            {f.id for f in (current.figures if current else [])}
            | {f.id for f in (job.figures if job else [])}
        )

    def _land(self, user: str, run_id: str, slot_id: str | None, build: FigureBuild) -> None:
        """그림 한 장 도착 — 파일 저장 → 작업에 넣기 → 요약·manifest 갱신."""
        self._save_build(user, run_id, build)  # type: ignore[attr-defined]
        taken = self._taken_ids(user, run_id)
        job = self._update_job(
            user, run_id, lambda j: job_rules.land(j, slot_id, build.figure, taken)[0]
        )
        if job is not None:
            self._refresh_figure_summary(user, run_id)

    def _refresh_figure_summary(self, user: str, run_id: str) -> None:
        from rra.application.services.run_manager import _figure_summary

        state = self.store.load_state(user, run_id)  # type: ignore[attr-defined]
        current = self._version(user, run_id, max(state.draft_version, 1))  # type: ignore[attr-defined]
        if current is not None:
            state.figures = _figure_summary(current.figures, state.figures)
        self._save(state)  # type: ignore[attr-defined]

    async def _execute_figures(self, user: str, run_id: str, claim: RunClaim) -> None:
        job: FigureJob | None = None
        error: str | None = None
        try:
            job = self._update_job(
                user,
                run_id,
                lambda j: j.model_copy(update={"status": "drawing", "started_at": self._clock()}),  # type: ignore[attr-defined]
            )
            if job is None:
                return
            await self._draw_slots(user, run_id, job)
        except Exception as exc:  # 그림 실패는 초안을 막지 않는다 — 사유 코드만
            error = type(exc).__name__
            logger.warning("figure.job_failed run=%s error=%s", run_id, error)
        except BaseException as exc:  # 취소(서버 종료) — 끝난 그림은 남기고 전파
            self._end_job(user, run_id, type(exc).__name__)
            claim.release()
            raise
        self._end_job(user, run_id, error)
        claim.release()

    def _end_job(self, user: str, run_id: str, error: str | None) -> None:
        """작업 끝 — 상태·시간 기록, 버전 파일에 그림 채우기, 단계·측정 갱신."""
        now = self._clock()  # type: ignore[attr-defined]
        job = self._update_job(user, run_id, lambda j: job_rules.finish(j, now, error=error))
        if job is None:
            return
        job = self._apply_job_to_versions(user, run_id, job)
        state = self.store.load_state(user, run_id)  # type: ignore[attr-defined]
        self._figure_step_status(state, job)
        if job.techniques is not None:
            state.figure_techniques = job.techniques
        self._fill_from_job(state, job)
        current = self._version(user, run_id, max(state.draft_version, 1))  # type: ignore[attr-defined]
        if current is not None:
            from rra.application.services.run_manager import _figure_summary

            state.figures = _figure_summary(current.figures, state.figures)
        self._touch_usage(user, run_id, state)  # type: ignore[attr-defined]
        self._save(state)  # type: ignore[attr-defined]
        logger.info(
            "figure.job_done run=%s status=%s figures=%d seconds=%s",
            run_id,
            job.status,
            len(job.figures),
            job.figures_done_seconds,
        )

    def _figure_step_status(self, state: RunState, job: FigureJob) -> None:
        try:
            step = state.step(FIGURES)
        except KeyError:
            return
        skipped = sum(1 for s in job.slots if s.status == "skipped")
        step.sentences, step.dropped = len(job.figures), skipped
        step.finished_at = job.finished_at
        renderers = sorted({f.renderer for f in job.figures})
        step.fallback = ",".join(renderers) or None
        if job.status == "done":
            step.status, step.error = "done", None
        else:
            step.status, step.error = "error", job.error or "FigureJobFailed"

    def _apply_job_to_versions(self, user: str, run_id: str, job: FigureJob) -> FigureJob:
        """끝난 작업의 그림을 그동안 만든 버전 파일(base_version 이상)에 한 번 채운다.
        버전에 이미 있는 그림(제안자가 고친 것)이 이긴다. 그 뒤로는 합치지 않는다(applied)."""
        if job.applied:
            return job
        for n in self.store.list_versions(user, run_id):  # type: ignore[attr-defined]
            if n < job.base_version:
                continue
            raw = self.store.load_version(user, run_id, n)  # type: ignore[attr-defined]
            if raw is None:
                continue
            merged = job_rules.merge_figures(raw.figures, job.figures)
            if len(merged) != len(raw.figures):
                self.store.save_version(  # type: ignore[attr-defined]
                    user, run_id, raw.model_copy(update={"figures": merged})
                )
        job = job.model_copy(update={"applied": True})
        self.store.save_figure_job(user, run_id, job)  # type: ignore[attr-defined]
        return job

    async def _draw_slots(self, user: str, run_id: str, job: FigureJob) -> None:
        """기본 그림 자리마다 따로 그려 하나씩 도착시킨다(build_default 와 같은 채우기 규칙) +
        분석 기법 추천을 함께."""
        figures = self.figures  # type: ignore[attr-defined]
        base = self.store.load_version(user, run_id, job.base_version)  # type: ignore[attr-defined]
        if base is None:
            return
        sections = list(base.sections)
        req = self.store.load_request(user, run_id)  # type: ignore[attr-defined]
        snapshot = self.store.load_snapshot(user, run_id)  # type: ignore[attr-defined]
        scope = self.store.load_state(user, run_id).scope  # type: ignore[attr-defined]
        want = figures.config.max_default
        candidates = figures.plan(sections, req, snapshot, all_candidates=True)
        rest = candidates[want:]
        sem = asyncio.Semaphore(max(1, int(figures.config.concurrency)))

        async def draw_slot(slot_id: str, kind: str, section: str) -> bool:
            async with sem:
                try:
                    builds, skipped = await figures.build_all(
                        [(kind, section)],
                        sections,
                        req,
                        snapshot,
                        existing_ids=self._taken_ids(user, run_id),
                    )
                except Exception as exc:  # 렌더·저장 오류 — 이 자리만 실패
                    code = type(exc).__name__
                    logger.warning("figure.slot_failed run=%s kind=%s error=%s", run_id, kind, code)
                    self._update_job(
                        user, run_id, lambda j: job_rules.resolve(j, slot_id, "failed", code)
                    )
                    return False
            if not builds:
                reason = str(skipped[0]["reason"]) if skipped else "invalid"
                logger.info("figure.skipped run=%s kind=%s reason=%s", run_id, kind, reason)
                self._update_job(
                    user, run_id, lambda j: job_rules.resolve(j, slot_id, "skipped", reason)
                )
                return False
            self._land(user, run_id, slot_id, builds[0])
            return True

        async def defaults() -> None:
            slots = [s for s in job.slots if s.kind != "technique"]
            made = await asyncio.gather(*(draw_slot(s.slot_id, s.kind, s.section) for s in slots))
            deficit = want - sum(1 for ok in made if ok)
            if deficit <= 0 or not rest:
                return
            extra: list[tuple[str, str, str]] = []
            for kind, section in rest[:deficit]:  # 걸러진 만큼 우선순위 다음 종류로 한 번 채운다
                cur = self._figure_job(user, run_id)
                if cur is None:
                    break
                cur, sid = job_rules.add_slot(cur, kind, section)
                self.store.save_figure_job(user, run_id, cur)  # type: ignore[attr-defined]
                extra.append((sid, kind, section))
            await asyncio.gather(*(draw_slot(*e) for e in extra))

        async def techniques() -> None:
            slot = next((s for s in job.slots if s.kind == "technique"), None)
            if slot is None:
                return
            n = figure_rules.technique_slots(len(figures.plan(sections, req, snapshot)))
            builds, outcome = await self._recommend_safely(  # type: ignore[attr-defined]
                sections, req, snapshot, slots=n, scope=scope
            )
            for b in builds:
                self._land(user, run_id, None, b)
            if builds:
                status, reason = "done", None
            elif outcome.status == "failed":
                status, reason = "failed", outcome.reason or "failed"
            elif outcome.status == "filtered":
                status, reason = "skipped", "filtered"
            else:  # 해당 없음·꺼짐 — 카드 없이 끝 (추천 결과 줄이 사유를 보인다)
                status, reason = "done", None
            dumped = outcome.model_dump()

            def done(j: FigureJob) -> FigureJob:
                j = job_rules.resolve(j, slot.slot_id, status, reason)
                return j.model_copy(update={"techniques": dumped})

            self._update_job(user, run_id, done)

        await asyncio.gather(defaults(), techniques())

    # ── 작성 중 섹션 먼저 보기 (ADR 0045 [4]) ──────────────────
    async def sections_progress(self, user: str, run_id: str) -> dict[str, Any]:
        """생성 중에도 끝난 섹션(근거 검증을 통과해 저장된 체크포인트)을 읽기 전용으로.
        버전이 아니다 — 마무리 정리(Q6)·L2 대조 전 글이다. 아직 안 끝난 섹션은 pending."""
        from rra.application.services.run_manager import _cleaned

        state = await self.status(user, run_id)  # type: ignore[attr-defined]
        stored = self.store.load_sections(user, run_id)  # type: ignore[attr-defined]
        done = [_cleaned(stored[k]) for k in state.section_keys if k in stored]
        return {
            "status": state.status,
            "sections": [{"key": s.key, "sentences": [x.text for x in s.sentences]} for s in done],
            "pending": [k for k in state.section_keys if k not in stored],
        }
