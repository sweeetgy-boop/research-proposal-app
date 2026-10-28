"""상태 표시는 버전을 만들지 않는다 (항목 21, ADR 0042) — RunManager 에 섞어 쓰는 메서드 묶음.

그림 확인함·추천 그림 결정·근거 승인/제외·선택형 확정·로컬 검토 제안 [무시] 는 현재 버전의 표시 파일
(versions/marks_vN.json)에 쌓는다. 버전 파일은 바꾸지 않는다. 읽기(_version·_current_version)는 버전
+
표시를 합쳐 돌려주므로 화면·제출 전 점검·마무리(HWPX)는 늘 최신 표시를 본다. 내용이 바뀌는 동작은
합친 현재 버전에서 새 버전을 만들므로 표시가 새 버전에 이어진다.

RunManager 의 저장소·상태 저장(_refresh_problems·_touch_usage·_save)을 그대로 쓴다.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

from rra.domain.models import DraftVersion, EvidenceDecision, Figure, VersionMarks
from rra.domain.rules import status_marks
from rra.domain.rules.evidence import evidence_counts
from rra.domain.rules.version_history import VersionRow, figure_name, version_rows
from rra.domain.rules.writer import local_sections

if TYPE_CHECKING:  # pragma: no cover
    from rra.domain.models import RunState


class StatusMarksMixin:
    """RunManager 전용 — self.store·status·_current_version·_refresh_problems·_save 를 쓴다."""

    # ── 읽기: 버전 + 표시 ────────────────────────────────
    def _version(self, user: str, run_id: str, n: int) -> DraftVersion | None:
        """버전 파일 + 그 버전의 상태 표시. 없으면 None."""
        found = self.store.load_version(user, run_id, n) if n >= 1 else None  # type: ignore[attr-defined]
        if found is None:
            return None
        return status_marks.apply_marks(found, self.store.load_marks(user, run_id, n))  # type: ignore[attr-defined]

    def _technique_labels(self) -> dict[str, str]:
        figures = getattr(self, "figures", None)
        catalog = getattr(figures, "catalog", None)
        return {t.key: t.label for t in getattr(catalog, "items", ()) or ()}

    def _figure_name(self, figure: Figure) -> str:
        return figure_name(figure, self._technique_labels())

    # ── 쓰기: 표시 저장 → 알림·그림 요약·측정 갱신 (버전 번호 그대로) ──────────
    def _after_marks(self, user: str, run_id: str, state: RunState) -> DraftVersion:
        from rra.application.services.run_manager import _figure_summary

        version = self._current_version(user, run_id, state)  # type: ignore[attr-defined]
        self._refresh_problems(user, run_id, state)  # type: ignore[attr-defined]
        state.figures = _figure_summary(version.figures, state.figures)
        self._touch_usage(  # type: ignore[attr-defined]
            user,
            run_id,
            state,
            counts=evidence_counts(version.sections, version.evidence_decisions),
        )
        self._save(state)  # type: ignore[attr-defined]
        return version

    def _save_figure_mark(
        self,
        user: str,
        run_id: str,
        state: RunState,
        current: DraftVersion,
        fig: Figure,
        action: str,
    ) -> DraftVersion:
        """그림 [확인함]·추천 그림 [넣기 확정]·[필요 없음]·[다시 넣기] — 새 버전 없이 표시만."""
        marks = status_marks.mark_figure(
            self.store.load_marks(user, run_id, current.version),  # type: ignore[attr-defined]
            current.version,
            fig,
            action,
            label=self._figure_name(fig),
            at=self._clock(),  # type: ignore[attr-defined]
        )
        self.store.save_marks(user, run_id, marks)  # type: ignore[attr-defined]
        return self._after_marks(user, run_id, state)

    def _save_evidence_marks(
        self,
        user: str,
        run_id: str,
        state: RunState,
        current: DraftVersion,
        merged: list[EvidenceDecision],
    ) -> DraftVersion:
        """근거 승인·제외 — 새 버전 없이 표시만. 바뀐 판단이 없으면 현재 버전 그대로."""
        changed = status_marks.new_decisions(current.evidence_decisions, merged)
        if not changed:
            return current
        marks = status_marks.mark_evidence(
            self.store.load_marks(user, run_id, current.version),  # type: ignore[attr-defined]
            current.version,
            merged,
            changed,
            at=self._clock(),  # type: ignore[attr-defined]
        )
        self.store.save_marks(user, run_id, marks)  # type: ignore[attr-defined]
        return self._after_marks(user, run_id, state)

    def _log_mark(
        self,
        user: str,
        run_id: str,
        state: RunState,
        kind: str,
        *,
        target: str = "",
        label: str = "",
    ) -> None:
        """기록만 남는 표시(선택형 확정·검토 제안 [무시]) — 현재 버전의 확인 기록에 한 줄."""
        n = state.draft_version
        if n < 1 or self.store.load_version(user, run_id, n) is None:  # type: ignore[attr-defined]
            return
        marks = status_marks.add_log(
            self.store.load_marks(user, run_id, n),  # type: ignore[attr-defined]
            n,
            kind,
            target=target,
            label=label,
            at=self._clock(),  # type: ignore[attr-defined]
        )
        self.store.save_marks(user, run_id, marks)  # type: ignore[attr-defined]

    async def record_mark(
        self, user: str, run_id: str, kind: str, *, target: str = "", label: str = ""
    ) -> None:
        """다른 기능이 쓰는 표시 기록(예: 레인 B 로컬 검토 제안 [무시] → kind="suggestion_ignore").
        버전을 만들지 않는다."""
        state = await self.status(user, run_id)  # type: ignore[attr-defined]
        self._log_mark(user, run_id, state, kind, target=target, label=label)

    # ── ⑤ 최종 검토 [취소] ─────────────────────────────────
    async def cancel_final_review(self, user: str, run_id: str) -> RunState:
        """진행 중인 최종 검토(Argon)만 멈춘다 — 검토 전 상태로 돌아가고 결과·버전은 남지 않는다."""
        from rra.application.services.run_manager import EditRejected

        state = await self.status(user, run_id)  # type: ignore[attr-defined]
        if state.status != "final_reviewing":
            raise EditRejected("진행 중인 최종 검토가 없습니다.")
        key = self._review_tasks.get(run_id)  # type: ignore[attr-defined]
        runner = self.runner  # type: ignore[attr-defined]
        if key is None or not runner.is_running(key) or not runner.cancel(key):
            raise EditRejected(
                "이 서버에서 진행 중인 최종 검토가 아닙니다 — 잠시 뒤 다시 보십시오."
            )
        # 취소된 작업이 끝날 때까지만 기다린다 (취소 예외는 정상)
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await runner.wait(key)
        return await self.status(user, run_id)  # type: ignore[attr-defined]

    # ── 버전 목록 ───────────────────────────────────────
    async def version_history(
        self, user: str, run_id: str
    ) -> tuple[list[DraftVersion], list[VersionRow]]:
        """버전(표시 합침)과 설명 줄(실제로 바뀐 섹션·그림, 확인 기록, 예전 상태만 바뀐 버전 접기,
        v1 작성자)."""
        state = await self.status(user, run_id)  # type: ignore[attr-defined]
        self._current_version(user, run_id, state)  # type: ignore[attr-defined]
        raw: list[DraftVersion] = []
        marks: dict[int, VersionMarks] = {}
        for n in self.store.list_versions(user, run_id):  # type: ignore[attr-defined]
            v = self.store.load_version(user, run_id, n)  # type: ignore[attr-defined]
            if v is None:
                continue
            raw.append(v)
            m = self.store.load_marks(user, run_id, n)  # type: ignore[attr-defined]
            if m is not None:
                marks[n] = m
        rows = version_rows(
            raw,
            marks,
            technique_labels=self._technique_labels(),
            writer=getattr(state, "writer", None),
            local_sections=len(local_sections(state.writers or {}, state.section_keys)),
        )
        merged = [status_marks.apply_marks(v, marks.get(v.version)) for v in raw]
        return merged, rows
