"""평가 기록 집계 — 선택 기록·과제안 측정 줄의 개수만 센다 (2026-11-04, ADR 0056 덧붙임).

- 시험 계정 줄(`test: true`, 배포 확인용 임시 사번 세션)은 기본으로 세지 않는다. 줄은 지우지 않고
  남아 있으므로(추적용) `include_test=True` 로 함께 셀 수 있다.
- 결과는 개수·열거값·중앙값뿐이다. doc_id·아이디어 해시·시각·점수 같은 줄 내용은 담지 않는다.
  문자열 칸은 정해진 열거값(event·source)이거나 짧은 영문 식별자(provider)만 이름으로 세고,
  그 밖은 "기타", 키가 없으면 "없음"으로 센다.
"""

from __future__ import annotations

import statistics
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from rra.domain.rules.recommend_metrics import TEST_FIELD, enum_value
from rra.domain.rules.similar_choice import EVENTS, SOURCE_AI_PREFILL, SOURCE_USER

NONE_LABEL = "없음"  # 키가 없는 옛 줄 (event·source 도입 전)
OTHER_LABEL = "기타"  # 열거값 밖 (손으로 고친 줄 등) — 값은 내보내지 않는다
SOURCES = (SOURCE_USER, SOURCE_AI_PREFILL)


def is_test_line(row: Mapping[str, Any]) -> bool:
    """시험 계정 줄인가 — `test` 가 정확히 true 일 때만."""
    return row.get(TEST_FIELD) is True


def _bucket(value: object, known: Iterable[str]) -> str:
    if value is None:
        return NONE_LABEL
    return value if isinstance(value, str) and value in tuple(known) else OTHER_LABEL


def _ordered(counter: Counter[str], first: Iterable[str]) -> dict[str, int]:
    """정해진 순서(열거값 → 기타 → 없음), 0건 열거값도 보인다."""
    keys = [*first, OTHER_LABEL, NONE_LABEL]
    out = {k: counter.get(k, 0) for k in first}
    for k in keys[len(tuple(first)) :]:
        if counter.get(k):
            out[k] = counter[k]
    return out


@dataclass(frozen=True)
class ChoiceStats:
    """선택 기록(feedback/similar_choices.jsonl) 집계."""

    found: bool = False
    total: int = 0  # 센 줄 (include_test 가 아니면 시험 줄 제외)
    test_lines: int = 0  # 파일 안의 시험 계정 줄
    include_test: bool = False
    unreadable: int = 0  # JSON 이 아닌 줄
    by_event: dict[str, int] = field(default_factory=dict)
    by_source: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class MetricsStats:
    """과제안 측정(cache/recommend_metrics.jsonl, 회전한 .1 포함) 집계."""

    found: bool = False
    total: int = 0
    test_lines: int = 0
    include_test: bool = False
    unreadable: int = 0
    by_provider: dict[str, int] = field(default_factory=dict)
    fallback_local: int = 0
    median_seconds: float | None = None


def choice_stats(rows: Iterable[Mapping[str, Any]], *, include_test: bool = False) -> ChoiceStats:
    """선택 기록 줄 → 개수. event 가 없는 옛 줄은 "없음"(그때는 생성 요청만 기록했다)."""
    events: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    total = tests = 0
    for row in rows:
        if is_test_line(row):
            tests += 1
            if not include_test:
                continue
        total += 1
        events[_bucket(row.get("event"), EVENTS)] += 1
        sources[_bucket(row.get("source"), SOURCES)] += 1
    return ChoiceStats(
        found=True,
        total=total,
        test_lines=tests,
        include_test=include_test,
        by_event=_ordered(events, EVENTS),
        by_source=_ordered(sources, SOURCES),
    )


def _seconds(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if value >= 0 else None


def metrics_stats(rows: Iterable[Mapping[str, Any]], *, include_test: bool = False) -> MetricsStats:
    """측정 줄 → 개수·provider 별·로컬 대체 수·seconds 중앙값."""
    providers: Counter[str] = Counter()
    seconds: list[float] = []
    total = tests = fallback = 0
    for row in rows:
        if is_test_line(row):
            tests += 1
            if not include_test:
                continue
        total += 1
        raw = row.get("provider")
        providers[NONE_LABEL if raw is None else (enum_value(raw) or OTHER_LABEL)] += 1
        if row.get("fallback_local") is True:
            fallback += 1
        sec = _seconds(row.get("seconds"))
        if sec is not None:
            seconds.append(sec)
    named = sorted(k for k in providers if k not in (OTHER_LABEL, NONE_LABEL))
    return MetricsStats(
        found=True,
        total=total,
        test_lines=tests,
        include_test=include_test,
        by_provider=_ordered(providers, named),
        fallback_local=fallback,
        median_seconds=round(statistics.median(seconds), 2) if seconds else None,
    )
