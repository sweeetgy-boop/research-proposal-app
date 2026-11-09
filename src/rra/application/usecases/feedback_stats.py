"""평가 기록 집계 유스케이스 — `rra feedback stats` (2026-11-04, ADR 0056 덧붙임).

선택 기록·과제안 측정 파일을 읽기만 하고(FeedbackReaderPort) 개수만 낸다
(`domain/rules/feedback_stats`). 시험 계정 줄(`test: true`)은 기본으로 세지 않는다 — 줄은 파일에
남아 있고 `include_test=True` 면 함께 센다. 출력 줄에는 doc_id·해시·시각 같은 줄 내용이 없다.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from rra.application.ports.feedback_reader import FeedbackReaderPort
from rra.domain.rules.feedback_stats import (
    ChoiceStats,
    MetricsStats,
    choice_stats,
    metrics_stats,
)

CHOICE_LABEL = "선택 기록 (feedback/similar_choices.jsonl)"
METRICS_LABEL = "과제안 측정 (cache/recommend_metrics.jsonl)"
STAGE_LABELS = {
    "seconds_search": "검색",
    "seconds_analogy": "유추",
    "seconds_generate": "생성",
}


def _counts(values: dict[str, int]) -> str:
    return ", ".join(f"{k} {v}" for k, v in values.items()) or "없음"


def _head(total: int, tests: int, include: bool, unreadable: int) -> list[str]:
    whole = total if include else total + tests
    mode = "포함" if include else "제외"
    lines = [f"  전체 줄: {whole}건, 시험 계정 줄: {tests}건 ({mode}), 센 줄: {total}건"]
    if unreadable:
        lines.append(f"  읽지 못한 줄: {unreadable}건 (세지 않음)")
    return lines


@dataclass(frozen=True)
class FeedbackReport:
    choices: ChoiceStats
    metrics: MetricsStats

    def as_lines(self) -> list[str]:
        c, m = self.choices, self.metrics
        lines = [CHOICE_LABEL]
        if not c.found:
            lines.append("  파일 없음")
        else:
            lines += _head(c.total, c.test_lines, c.include_test, c.unreadable)
            lines.append(f"  시점(event): {_counts(c.by_event)}")
            lines.append(f"  출처(source): {_counts(c.by_source)}")
        lines.append(METRICS_LABEL)
        if not m.found:
            lines.append("  파일 없음")
        else:
            lines += _head(m.total, m.test_lines, m.include_test, m.unreadable)
            lines.append(f"  provider: {_counts(m.by_provider)}")
            lines.append(f"  로컬 대체(fallback_local): {m.fallback_local}건")
            median = "없음" if m.median_seconds is None else f"{m.median_seconds:g}초"
            lines.append(f"  seconds 중앙값: {median}")
            if m.by_branch:
                lines.append(f"  갈래(branch): {_counts(m.by_branch)}")
            stages = {k: v for k, v in m.median_stage_seconds.items() if v is not None}
            if stages:  # 2026-11-09 단계별 초 칸이 있는 줄만 (옛 줄은 빠진다)
                lines.append(
                    "  단계 중앙값: "
                    + " · ".join(f"{STAGE_LABELS.get(k, k)} {v:g}초" for k, v in stages.items())
                )
        if not (c.include_test and m.include_test) and (c.test_lines or m.test_lines):
            lines.append("(시험 계정 줄까지 세려면 --include-test)")
        return lines


class FeedbackStats:
    def __init__(self, reader: FeedbackReaderPort):
        self.reader = reader

    def __call__(self, *, include_test: bool = False) -> FeedbackReport:
        choice = self.reader.choice_rows()
        metric = self.reader.metrics_rows()
        c = (
            replace(
                choice_stats(choice.rows, include_test=include_test),
                unreadable=choice.unreadable,
            )
            if choice.found
            else ChoiceStats(include_test=include_test)
        )
        m = (
            replace(
                metrics_stats(metric.rows, include_test=include_test),
                unreadable=metric.unreadable,
            )
            if metric.found
            else MetricsStats(include_test=include_test)
        )
        return FeedbackReport(choices=c, metrics=m)
