from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable


@runtime_checkable
class RecommendMetricsPort(Protocol):
    """차별화 과제안 측정 기록 (ADR 0055 덧붙임) — 추천 호출 한 번에 한 줄.

    record(row): row 는 `domain/rules/recommend_metrics.metrics_row` 의 결과(ts 제외,
    건수·시간·열거값만). 구현이 시각(ts)을 붙인다. 기록 실패는 추천을 막지 않는다(구현이
    OSError 를 삼키고, 유스케이스도 감싼다). 본문·제목·doc_id·사용자 id 는 담지 않는다(보안 D).
    """

    def record(self, row: Mapping[str, object]) -> None: ...
