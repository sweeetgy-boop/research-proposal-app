"""② 유사과제 선택 기록 포트 (2026-10-28 레인 A) — 임계치 조정용 JSONL.

한 줄 = 선택한 행 하나 {at, idea(해시), doc_id, choice, 점수·판정}. 원문·개인정보 없음
(domain/rules/similar_choice.choice_records 가 만든다).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ChoiceLogPort(Protocol):
    def append(self, records: list[dict[str, Any]]) -> None: ...
