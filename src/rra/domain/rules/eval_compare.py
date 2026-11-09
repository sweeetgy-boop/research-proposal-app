"""평가 결과 비교 (ADR 0058, `rra eval compare`) — 두 개 이상의 EvalResult → 표 행. 순수 함수.

첫 결과가 기준(가). 다른 열은 기준과의 차이와 판정을 낸다:
- 두 열 모두 ci95 가 있고 구간이 겹치면 "차이 없음" — 겹치지 않으면 방향에 따라 "개선"/"악화"
  (낮을수록 좋은 지표는 `LOWER_IS_BETTER`).
- 어느 한쪽이라도 ci95 가 없으면(반복 1회·L0) "구간 없음" — 차이 값만 보인다.
- 값이 없는 지표는 "—".
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from rra.domain.models.eval_result import CI95, METRIC_KEYS, EvalResult

LOWER_IS_BETTER: frozenset[str] = frozenset(
    {"false_block", "latency_p50", "latency_p90", "rec_zero_rate", "novel_estimated_barrier_ratio"}
)
METRIC_LABELS: dict[str, str] = {
    "recall_at5": "역방향 정답 상위 5 적중률 (recall_at5)",
    "false_block": "함정 차단율 (false_block, 낮을수록 좋음)",
    "novel_rate": "새 영역 novel 판정률 (novel_rate)",
    "novel_estimated_barrier_ratio": "novel 장벽 '추정' 비율 (낮을수록 좋음)",
    "latency_p50": "② 지연 중앙값 초 (latency_p50)",
    "latency_p90": "② 지연 p90 초 (latency_p90)",
    "rec_zero_rate": "과제안 0건 비율 (rec_zero_rate, 낮을수록 좋음)",
}
VERDICT_SAME = "차이 없음"
VERDICT_BETTER = "개선"
VERDICT_WORSE = "악화"
VERDICT_NO_CI = "구간 없음"
VERDICT_NA = "—"


@dataclass(frozen=True)
class CompareRow:
    metric: str
    label: str
    values: list[float | None] = field(default_factory=list)  # 결과 순서
    cis: list[CI95 | None] = field(default_factory=list)
    diffs: list[float | None] = field(default_factory=list)  # 기준(첫 열) 대비, 첫 열은 None
    verdicts: list[str] = field(default_factory=list)  # 첫 열은 ""


def _overlap(a: CI95, b: CI95) -> bool | None:
    if None in (a.low, a.high, b.low, b.high):
        return None
    return not (a.high < b.low or b.high < a.low)  # type: ignore[operator]


def verdict(metric: str, base: float | None, other: float | None, a: CI95 | None, b: CI95 | None):
    if base is None or other is None:
        return VERDICT_NA
    if a is None or b is None:
        return VERDICT_NO_CI
    overlap = _overlap(a, b)
    if overlap is None:
        return VERDICT_NO_CI
    if overlap:
        return VERDICT_SAME
    improved = other < base if metric in LOWER_IS_BETTER else other > base
    return VERDICT_BETTER if improved else VERDICT_WORSE


def compare(results: Sequence[EvalResult]) -> list[CompareRow]:
    rows: list[CompareRow] = []
    for key in METRIC_KEYS:
        values = [getattr(r.metrics, key) for r in results]
        cis = [r.ci95.get(key) for r in results]
        base = values[0] if values else None
        diffs: list[float | None] = [None]
        verdicts: list[str] = [""]
        for v, c in zip(values[1:], cis[1:], strict=True):
            diffs.append(round(v - base, 4) if (v is not None and base is not None) else None)
            verdicts.append(verdict(key, base, v, cis[0], c))
        rows.append(
            CompareRow(
                metric=key,
                label=METRIC_LABELS.get(key, key),
                values=values,
                cis=cis,
                diffs=diffs,
                verdicts=verdicts,
            )
        )
    return rows


def column_labels(results: Sequence[EvalResult]) -> list[str]:
    """열 이름 — label 이 있으면 그것, 없으면 suite·commit."""
    out: list[str] = []
    for i, r in enumerate(results):
        name = r.label or f"{r.suite} {r.commit or ''}".strip()
        out.append(name if name not in out else f"{name} ({i + 1})")
    return out


def gate(
    base: EvalResult,
    new: EvalResult,
    *,
    max_recall_drop: float = 0.05,
    max_false_block_rise: float = 0.05,
) -> list[str]:
    """L0 게이트(계약 §6) — 넘은 항목의 설명 목록 (비면 통과). 값이 없는 쪽은 비교하지 않는다."""
    failures: list[str] = []
    b, n = base.metrics, new.metrics
    if b.recall_at5 is not None and n.recall_at5 is not None:
        drop = b.recall_at5 - n.recall_at5
        if drop > max_recall_drop:
            failures.append(
                f"recall_at5 {b.recall_at5:.3f} → {n.recall_at5:.3f} "
                f"(−{drop:.3f} > {max_recall_drop})"
            )
    if b.false_block is not None and n.false_block is not None:
        rise = n.false_block - b.false_block
        if rise > max_false_block_rise:
            failures.append(
                f"false_block {b.false_block:.3f} → {n.false_block:.3f} "
                f"(+{rise:.3f} > {max_false_block_rise})"
            )
    return failures


# ── 짝 비교 (같은 문제 묶음을 두 구성으로, 2026-11-09 사용자 보완) ───────────────
@dataclass(frozen=True)
class PairedStats:
    """기준(a)·비교(b)의 문제별 맞힘 대조. `discordant_ids` 는 두 구성의 결과가 갈린 문제 id —
    그 문제만 3회 반복해 다시 잰다(`rra eval run --ids`)."""

    n_common: int
    both_correct: int
    a_only: int  # 기준만 맞힘
    b_only: int  # 비교만 맞힘
    both_wrong: int
    mcnemar_p: float | None  # 정확 이항 양측 p (갈린 문제 0건이면 None)
    by_kind: dict[str, tuple[int, int, int, int]] = field(
        default_factory=dict
    )  # kind → (둘다, a만, b만, 둘다틀림)
    discordant_ids: tuple[str, ...] = ()

    @property
    def verdict(self) -> str:
        if self.mcnemar_p is None:
            return VERDICT_SAME if self.n_common else VERDICT_NA
        if self.mcnemar_p < 0.05:
            return VERDICT_BETTER if self.b_only > self.a_only else VERDICT_WORSE
        return VERDICT_SAME


def mcnemar_exact(a_only: int, b_only: int) -> float | None:
    """McNemar 정확 검정(양측) — 갈린 문제 수가 적을 때 맞는 이항 검정. b+c=0 이면 None."""
    n = a_only + b_only
    if n == 0:
        return None
    k = min(a_only, b_only)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2**n)
    return round(min(1.0, 2 * tail), 4)


def paired(a: EvalResult, b: EvalResult) -> PairedStats | None:
    """두 결과가 같은 문제 id 를 공유할 때만 — 아니면 None(짝 비교 불가)."""
    ra = {p.id: p for p in a.problems if p.correct is not None}
    rb = {p.id: p for p in b.problems if p.correct is not None}
    common = sorted(set(ra) & set(rb))
    if not common:
        return None
    both = a_only = b_only = wrong = 0
    kinds: dict[str, list[int]] = {}
    disc: list[str] = []
    for pid in common:
        ca, cb = ra[pid].correct, rb[pid].correct
        cell = kinds.setdefault(ra[pid].kind, [0, 0, 0, 0])
        if ca and cb:
            both += 1
            cell[0] += 1
        elif ca:
            a_only += 1
            cell[1] += 1
            disc.append(pid)
        elif cb:
            b_only += 1
            cell[2] += 1
            disc.append(pid)
        else:
            wrong += 1
            cell[3] += 1
    return PairedStats(
        n_common=len(common),
        both_correct=both,
        a_only=a_only,
        b_only=b_only,
        both_wrong=wrong,
        mcnemar_p=mcnemar_exact(a_only, b_only),
        by_kind={k: tuple(v) for k, v in sorted(kinds.items())},  # type: ignore[misc]
        discordant_ids=tuple(disc),
    )
