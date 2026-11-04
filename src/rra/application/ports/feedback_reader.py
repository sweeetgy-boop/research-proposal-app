"""평가 기록 읽기 포트 (2026-11-04, ADR 0056 덧붙임) — `rra feedback stats` 가 개수만 센다.

선택 기록(feedback/similar_choices.jsonl)과 과제안 측정(cache/recommend_metrics.jsonl, 회전한 `.1`
포함)을 읽기만 한다. 쓰기·지우기 없음. 줄 내용은 집계 규칙(`domain/rules/feedback_stats`)에만
건네고 출력하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class JsonlRows:
    """읽은 줄 — repr 에 내용 없음. found 는 파일이 하나라도 있었는가, unreadable 은 JSON
    객체가 아닌 줄 수."""

    rows: tuple[dict[str, Any], ...] = field(default=(), repr=False)
    found: bool = False
    unreadable: int = 0

    def __repr__(self) -> str:
        return f"JsonlRows(n={len(self.rows)}, found={self.found}, unreadable={self.unreadable})"


@runtime_checkable
class FeedbackReaderPort(Protocol):
    def choice_rows(self) -> JsonlRows:
        """선택 기록 줄 (없으면 found=False)."""
        ...

    def metrics_rows(self) -> JsonlRows:
        """과제안 측정 줄 — 회전한 `.1` 먼저, 지금 파일 다음."""
        ...
