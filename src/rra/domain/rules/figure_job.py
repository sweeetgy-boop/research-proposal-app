"""그림 백그라운드 작업 규칙(ADR 0045) — 순수 함수.

- 자리(slot): 계획한 그림마다 하나. drawing → done(그림 도착) | failed(호출 실패·서버 재시작) |
  skipped(명세가 규칙에 걸러짐).
- 합치기: 버전에 이미 있는 그림이 이긴다(제안자가 그 그림을 고쳤을 수 있다). 작업 그림 중 버전에
  없는 id 만 덧붙인다.
- 작업 상태: 자리가 다 끝나면 done(일부 자리가 실패해도 — 그 카드가 사유와 [다시 그리기]를
  보인다). 작업 전체가 깨졌으면(예외·서버 재시작) failed.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime

from rra.domain.models.figure import Figure, display_name
from rra.domain.models.figure_job import FigureJob, FigureSlot
from rra.domain.rules.figures import next_figure_id

ACTIVE_JOB: frozenset[str] = frozenset({"pending", "drawing"})
INTERRUPTED = "interrupted"
# 그리는 중에 막는 동작의 안내 (화면 문구)
PENDING_FINISH_HINT = "그림 준비 중 — 끝나면 진행할 수 있습니다."
PENDING_FIGURE_HINT = "이 그림은 아직 그리는 중입니다 — 준비되면 확인·수정할 수 있습니다."
PENDING_ADD_HINT = "그림을 그리는 중입니다 — 끝난 뒤 그림을 추가하거나 다시 추천받을 수 있습니다."
TECHNIQUE_SLOT_NAME = "분석 기법 추천 그림"

# 자리 실패·건너뜀 사유 → 카드 한 줄 (코드·영어를 화면에 내보내지 않는다)
_REASON_LABELS: dict[str, str] = {
    INTERRUPTED: "서버가 다시 시작되어 그리지 못했습니다 (호출 실패).",
    "CancelledError": "그리기가 취소되었습니다 (호출 실패).",
    "skip": "이 내용으로는 그릴 그림이 없습니다 (해당 없음).",
    "none": "추천할 분석 기법이 없습니다 (해당 없음).",
    "filtered": "분석 결과가 출처 검사를 통과하지 못했습니다 (규칙에 걸러짐).",
}


def reason_label(reason: str | None, status: str) -> str | None:
    """자리 사유 → 한국어 한 줄. 끝났거나 그리는 중이면 None."""
    if status in ("drawing", "done"):
        return None
    if reason in _REASON_LABELS:
        return _REASON_LABELS[reason]
    if status == "skipped" or (reason or "").startswith(("figure_", "technique_", "invalid")):
        return "본문·근거 글자로 그림을 만들지 못했습니다 (규칙에 걸러짐)."
    return "그림을 그리지 못했습니다 (호출 실패)."


def seconds_between(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        a, b = datetime.fromisoformat(start), datetime.fromisoformat(end)
    except ValueError:
        return None
    return max(0.0, round((b - a).total_seconds(), 1))


def new_job(
    plan: Sequence[tuple[str, str]],
    *,
    technique_slot: bool,
    base_version: int,
    now: str,
    submitted_at: str | None,
    review_after: bool = False,
) -> FigureJob:
    """계획(종류, 섹션) → 자리. 분석 기법은 개수를 모르므로(0~2) 자리 하나로 둔다."""
    slots = [
        FigureSlot(slot_id=f"slot-{i}", kind=kind, section=section, display_name=display_name(kind))
        for i, (kind, section) in enumerate(plan, start=1)
    ]
    if technique_slot:
        slots.append(
            FigureSlot(
                slot_id=f"slot-{len(slots) + 1}",
                kind="technique",
                section="",
                display_name=TECHNIQUE_SLOT_NAME,
            )
        )
    return FigureJob(
        status="pending",
        base_version=base_version,
        slots=slots,
        created_at=now,
        submitted_at=submitted_at,
        draft_visible_seconds=seconds_between(submitted_at, now),
        review_after=review_after,
    )


def add_slot(job: FigureJob, kind: str, section: str) -> tuple[FigureJob, str]:
    """채우기(우선순위 다음 종류) 자리를 덧붙인다 → (작업, slot_id)."""
    sid = f"slot-{len(job.slots) + 1}"
    slot = FigureSlot(slot_id=sid, kind=kind, section=section, display_name=display_name(kind))
    return job.model_copy(update={"slots": [*job.slots, slot]}), sid


def _update_slot(job: FigureJob, slot_id: str, **fields: object) -> FigureJob:
    slots = [s.model_copy(update=fields) if s.slot_id == slot_id else s for s in job.slots]
    return job.model_copy(update={"slots": slots})


def land(
    job: FigureJob, slot_id: str | None, figure: Figure, taken: Iterable[str] = ()
) -> tuple[FigureJob, Figure]:
    """그림 한 장 도착 — id 가 이미 있는 그림(작업·현재 버전)과 겹치면 새 id 를 준다.
    slot_id 가 None 이면 자리 없이(분석 기법 추천처럼 개수를 몰랐던 그림) 덧붙인다."""
    ids = {f.id for f in job.figures} | set(taken)
    if figure.id in ids:
        prefix = "t" if figure.kind == "technique" else ""
        figure = figure.model_copy(
            update={"id": next_figure_id(figure.section, ids, prefix=prefix)}
        )
    job = job.model_copy(update={"figures": [*job.figures, figure]})
    if slot_id is not None:
        job = _update_slot(job, slot_id, status="done", figure_id=figure.id, reason=None)
    return job, figure


def resolve(job: FigureJob, slot_id: str, status: str, reason: str | None) -> FigureJob:
    """자리를 failed·skipped·done(그림 없이 끝남 — 기법 추천 0건)으로."""
    return _update_slot(job, slot_id, status=status, reason=reason)


def finish(job: FigureJob, now: str, *, error: str | None = None) -> FigureJob:
    """작업 끝 — 남은 자리는 실패로. 상태 done | failed, 끝난 시각·소요 시간."""
    reason = error or INTERRUPTED
    slots = [
        s.model_copy(update={"status": "failed", "reason": reason}) if s.status == "drawing" else s
        for s in job.slots
    ]
    status = "failed" if error is not None else "done"  # 자리별 실패는 카드가 사유를 보인다
    return job.model_copy(
        update={
            "slots": slots,
            "status": status,
            "error": error,
            "finished_at": now,
            "figures_done_seconds": seconds_between(job.submitted_at, now),
        }
    )


def interrupt(job: FigureJob, now: str) -> FigureJob:
    """서버 재시작 등으로 작업이 사라졌다 — 그리던 자리는 실패([다시 그리기])."""
    return finish(job, now, error=INTERRUPTED)


def merge_figures(version_figures: Sequence[Figure], job_figures: Sequence[Figure]) -> list[Figure]:
    """버전 그림 + 버전에 없는 작업 그림 (버전 쪽이 이긴다). 작업 그림은 id 순으로 덧붙인다."""
    have = {f.id for f in version_figures}
    extra = [f for f in job_figures if f.id not in have]
    return [*version_figures, *sorted(extra, key=lambda f: f.id)]


def open_slots(job: FigureJob | None) -> list[FigureSlot]:
    """카드로 보일 자리 — 그리는 중·실패. 건너뛴 자리는 그림이 한 장도 없을 때만(빈 결과 금지)."""
    if job is None:
        return []
    shown = [s for s in job.slots if s.status in ("drawing", "failed")]
    if job.status not in ACTIVE_JOB and not job.figures:
        shown += [s for s in job.slots if s.status == "skipped"]
    return shown


def is_pending_slot(job: FigureJob | None, figure_id: str) -> bool:
    """figure_id 가 아직 그리는 중인 자리(slot-n)인가."""
    return job is not None and any(
        s.slot_id == figure_id and s.status == "drawing" for s in job.slots
    )
