"""U8 시범운영 측정의 순수 규칙 — 단계 시간, 근거 판단 비율, 집계."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from rra.domain.models import EvidenceCounts, RunState, UsageRecord


def _seconds(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        a = datetime.fromisoformat(start)
        b = datetime.fromisoformat(end)
    except ValueError:
        return None
    return max(0.0, round((b - a).total_seconds(), 3))


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def step_durations(state: RunState) -> dict[str, float]:
    """끝난 step 의 소요 시간(초).

    섹션 step 은 여러 개가 동시에 돈다(Argon 작성은 4개씩) — 'sections' 는 첫 섹션 시작부터 마지막
    섹션 끝까지의 실제 경과(벽시계), 'sections_sum' 은 섹션별 시간의 합(보조 지표)이다
    (2026-10-28 실측: 합 73초, 실제 20초).
    """
    out: dict[str, float] = {}
    starts: list[datetime] = []
    ends: list[datetime] = []
    total = 0.0
    for s in state.steps:
        sec = _seconds(s.started_at, s.finished_at)
        if sec is None:
            continue
        if s.name.startswith("section:"):
            total += sec
            a, b = _parse(s.started_at), _parse(s.finished_at)
            if a is not None and b is not None:
                starts.append(a)
                ends.append(b)
            continue
        out[s.name] = round(out.get(s.name, 0.0) + sec, 3)
    if starts and ends:
        out["sections"] = round(max(0.0, (max(ends) - min(starts)).total_seconds()), 3)
        out["sections_sum"] = round(total, 3)
    return out


def total_seconds(state: RunState) -> float | None:
    """만든 때부터 마무리(없으면 마지막 갱신)까지 — 제안자가 검토·수정한 시간을 포함한 전체 경과."""
    return _seconds(state.created_at, state.finalized_at or state.updated_at)


def refresh(
    record: UsageRecord,
    state: RunState,
    *,
    counts: dict[str, int] | None = None,
    now: str | None = None,
) -> UsageRecord:
    update: dict[str, Any] = {
        "step_seconds": step_durations(state),
        "total_seconds": total_seconds(state),
        "updated_at": now,
    }
    if counts is not None:
        update["evidence"] = EvidenceCounts(**counts)
    return record.model_copy(update=update)


def aggregate(records: Iterable[UsageRecord]) -> dict[str, Any]:
    """`rra usage report` — run 수, 평균 총 시간, 단계 평균, 근거 판단 비율 평균, 다시 쓰기 합,
    HWPX 성공 수, 만족도 평균·분포. 본문은 없다."""
    rows = list(records)
    n = len(rows)
    if n == 0:
        return {"runs": 0}
    totals = [r.total_seconds for r in rows if r.total_seconds is not None]
    steps: dict[str, list[float]] = {}
    for r in rows:
        for k, v in r.step_seconds.items():
            steps.setdefault(k, []).append(v)
    ratios = [r.evidence.ratios() for r in rows if r.evidence.total > 0]
    coverage = [r.checklist_coverage for r in rows if r.checklist_coverage is not None]
    scores = [r.satisfaction.score for r in rows if r.satisfaction is not None]
    dist = {str(i): scores.count(i) for i in range(1, 6)}
    return {
        "runs": n,
        "avg_total_seconds": round(sum(totals) / len(totals), 1) if totals else None,
        "avg_step_seconds": {k: round(sum(v) / len(v), 1) for k, v in sorted(steps.items())},
        "checklist_coverage_avg": round(sum(coverage) / len(coverage), 3) if coverage else None,
        "evidence_ratio_avg": {
            key: round(sum(r[key] for r in ratios) / len(ratios), 3)
            for key in ("approve", "replace", "exclude")
        }
        if ratios
        else None,
        "evidence_decided_runs": len(ratios),
        "rewrites_total": sum(r.rewrites for r in rows),
        "hwpx_success": sum(1 for r in rows if r.hwpx_success),
        "hwpx_failed": sum(1 for r in rows if r.hwpx_success is False),
        "satisfaction_avg": round(sum(scores) / len(scores), 2) if scores else None,
        "satisfaction_count": len(scores),
        "satisfaction_distribution": dist,
    }
