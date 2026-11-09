"""평가 지표 계산 (ADR 0058, 계약 docs/contracts/eval-results.md §2) — 순수 함수.

입력은 문제별·반복별 결과(`ProblemOutcome`)뿐이고 출력은 숫자뿐이다(본문·doc_id 없음).

- 비율 지표(recall_at5·false_block·novel_rate·rec_zero_rate): 문제마다 반복 평균을 내고, 그 문제별
  평균의 평균. 분모는 해당 종류의 문제 수(reverse → recall_at5, trap → false_block, novel →
  novel_rate·
  rec_zero_rate; novel 문제의 차단은 false_block 분모에 더하지 않고 notes 로 따로 센다).
- novel_estimated_barrier_ratio: novel 과제안의 장벽 중 '추정' 비율 — 장벽을 모두 더한 뒤 나눈다.
- latency_p50·p90: 모든 (문제, 반복) 벽시계 초의 백분위(선형 보간).
- ci95: 문제별 평균 벡터를 부트스트랩(복원 추출 `BOOTSTRAP_ITERS` 회, 고정 seed) 한 평균의
  2.5·97.5 백분위. 반복 ≥ 2 인 실행에서만 낸다(계약). 문제가 2개 미만이면 None.
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from rra.domain.models.eval_result import CI95, METRIC_KEYS, EvalMetrics

BOOTSTRAP_ITERS = 2000
RATE_METRICS: tuple[str, ...] = ("recall_at5", "false_block", "novel_rate", "rec_zero_rate")


@dataclass(frozen=True)
class ProblemOutcome:
    """문제 한 건, 한 번 실행의 결과 — 숫자·참거짓만."""

    kind: str  # reverse | trap | novel
    seconds: float
    hit: bool | None = None  # reverse: 정답이 상위 5행 안
    blocked: bool = False  # 차단 게이트(effective_blocking)
    novel: bool | None = None  # novel: recommend_mode == novel
    rec_zero: bool | None = None  # 과제안 0건 (과제안을 돌린 경우만)
    barriers_total: int = 0  # novel 과제안의 장벽 수
    barriers_estimated: int = 0  # 그중 '추정'
    llm_calls: int = 0
    cache_hits: int = 0


def mean(values: Iterable[float]) -> float | None:
    got = list(values)
    return sum(got) / len(got) if got else None


def percentile(values: Sequence[float], p: float) -> float | None:
    """선형 보간 백분위 (p 는 0~100)."""
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return float(xs[0])
    pos = (len(xs) - 1) * max(0.0, min(100.0, p)) / 100.0
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return float(xs[lo] + (xs[hi] - xs[lo]) * (pos - lo))


def bootstrap_ci95(values: Sequence[float], *, seed: int, iters: int = BOOTSTRAP_ITERS) -> CI95:
    """문제별 평균 벡터 → 평균의 95% 부트스트랩 구간. 값이 2개 미만이면 None 구간."""
    xs = [float(v) for v in values]
    if len(xs) < 2:
        return CI95()
    rng = random.Random(seed)  # noqa: S311 — 통계용 재현 가능한 난수
    n = len(xs)
    means = sorted(sum(rng.choice(xs) for _ in range(n)) / n for _ in range(max(1, iters)))
    low = percentile(means, 2.5)
    high = percentile(means, 97.5)
    return CI95(low=_r(low), high=_r(high))


def _r(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def _problem_means(
    outcomes: Sequence[Sequence[ProblemOutcome]], kind: str, field: str
) -> list[float]:
    """해당 종류 문제마다 반복 평균 (값이 None 인 반복은 뺀다)."""
    out: list[float] = []
    for runs in outcomes:
        vals = [
            float(getattr(r, field))
            for r in runs
            if r.kind == kind and getattr(r, field) is not None
        ]
        if vals:
            out.append(sum(vals) / len(vals))
    return out


def compute_metrics(
    outcomes: Sequence[Sequence[ProblemOutcome]], *, repeats: int, seed: int
) -> tuple[EvalMetrics, dict[str, CI95], list[str]]:
    """문제별 반복 결과 → (지표, ci95, 메모). outcomes[i] = i 번째 문제의 반복 결과 목록."""
    means_by: dict[str, list[float]] = {
        "recall_at5": _problem_means(outcomes, "reverse", "hit"),
        "false_block": _problem_means(outcomes, "trap", "blocked"),
        "novel_rate": _problem_means(outcomes, "novel", "novel"),
        "rec_zero_rate": [
            *_problem_means(outcomes, "reverse", "rec_zero"),
            *_problem_means(outcomes, "trap", "rec_zero"),
            *_problem_means(outcomes, "novel", "rec_zero"),
        ],
    }
    values: dict[str, float | None] = {k: _r(mean(v)) for k, v in means_by.items()}
    all_runs = [r for runs in outcomes for r in runs]
    barriers = sum(r.barriers_total for r in all_runs)
    estimated = sum(r.barriers_estimated for r in all_runs)
    values["novel_estimated_barrier_ratio"] = _r(estimated / barriers) if barriers else None
    seconds = [r.seconds for r in all_runs]
    values["latency_p50"] = _r(percentile(seconds, 50), 2)
    values["latency_p90"] = _r(percentile(seconds, 90), 2)
    metrics = EvalMetrics(**{k: values.get(k) for k in METRIC_KEYS})

    ci: dict[str, CI95] = {}
    if repeats >= 2:
        for i, key in enumerate(RATE_METRICS):
            if len(means_by[key]) >= 2:
                ci[key] = bootstrap_ci95(means_by[key], seed=seed * 7919 + i)
    notes: list[str] = []
    novel_blocked = _problem_means(outcomes, "novel", "blocked")
    if novel_blocked:
        blocked = sum(1 for v in novel_blocked if v > 0)
        notes.append(f"새 영역 문제 차단 {blocked}/{len(novel_blocked)}건 (false_block 분모 밖)")
    if repeats >= 2:
        notes.append(f"ci95: 문제별 반복 평균의 부트스트랩 {BOOTSTRAP_ITERS}회 (2.5·97.5 백분위)")
    return metrics, ci, notes


def count_kinds(outcomes: Sequence[Sequence[ProblemOutcome]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for runs in outcomes:
        if runs:
            out[runs[0].kind] = out.get(runs[0].kind, 0) + 1
    return out
