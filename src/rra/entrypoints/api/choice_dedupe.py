"""② 선택 기록 중복 한 줄 — 세션마다 마지막으로 기록한 서명 (ADR 0056 2026-11-04 후속).

규칙(서명·반복 판정·세션 키)은 `domain/rules/similar_choice` 에 있고, 여기는 상태만 둔다.
메모리에만, 최근 MAX 세션(LRU). API 프로세스를 다시 띄우면 잊는다(그 뒤 첫 기록은 다시 쓴다).
세션 키는 주체 키와 아이디어 해시의 해시라 주체 키 원문을 들고 있지 않다.
"""

from __future__ import annotations

from collections import OrderedDict

from rra.domain.rules.similar_choice import is_repeat


class ChoiceDedupe:
    MAX = 500

    def __init__(self, max_sessions: int = MAX) -> None:
        self.max_sessions = max_sessions
        self._last: OrderedDict[str, str] = OrderedDict()

    def is_repeat(self, key: str, signature: str | None) -> bool:
        """이 세션이 마지막으로 기록한 서명과 같으면 True (쓰지 않는다)."""
        last = self._last.get(key)
        if last is not None:
            self._last.move_to_end(key)
        return is_repeat(last, signature)

    def remember(self, key: str, signature: str | None) -> None:
        """기록에 성공한 서명을 이 세션의 마지막 서명으로. 서명이 없으면(줄 없음) 그대로."""
        if signature is None:
            return
        self._last[key] = signature
        self._last.move_to_end(key)
        while len(self._last) > self.max_sessions:
            self._last.popitem(last=False)

    def __len__(self) -> int:
        return len(self._last)
