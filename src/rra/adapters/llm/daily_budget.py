"""외부 LLM 일일 전체 호출 상한 (레인 A) — 파일 카운터 + LLM 래퍼.

- FileDailyBudget: `<path>` JSON {"date": "YYYY-MM-DD", "count": n}. 날짜가 바뀌면 0 부터.
  프로세스 간(API·CLI·MCP) 같은 파일을 보며, 쓰기는 스레드 락 + 원자적 교체.
- BudgetedLLM: LLMPort 를 감싸 호출마다 try_spend(). 상한이면 BudgetExhausted — 호출하지 않는다.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rra.adapters.runs._fs import ensure_dir, read_json, write_json
from rra.application.ports.auth import BudgetExhausted


def _today() -> str:
    return datetime.now(UTC).astimezone().date().isoformat()


class FileDailyBudget:
    def __init__(self, path: Path, limit: int, *, today: Callable[[], str] = _today):
        self.path = Path(path)
        self.limit = max(0, int(limit))
        self._today = today
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return f"FileDailyBudget({self.path}, limit={self.limit})"

    def _read(self) -> tuple[str, int]:
        if not self.path.exists():
            return self._today(), 0
        try:
            data = read_json(self.path)
            return str(data.get("date") or ""), int(data.get("count") or 0)
        except (ValueError, OSError):
            return self._today(), 0

    def _count(self) -> int:
        date, count = self._read()
        return count if date == self._today() else 0

    def try_spend(self, n: int = 1) -> bool:
        with self._lock:
            count = self._count()
            if count + n > self.limit:
                return False
            ensure_dir(self.path.parent)
            write_json(self.path, {"date": self._today(), "count": count + n})
            return True

    def exhausted(self) -> bool:
        with self._lock:
            return self._count() >= self.limit

    def remaining(self) -> int:
        with self._lock:
            return max(0, self.limit - self._count())


class BudgetedLLM:
    """LLMPort 래퍼 — 호출 전에 예산을 쓴다. 그 밖의 속성(aclose·list_models)은 안쪽으로 위임."""

    def __init__(self, inner: Any, budget: FileDailyBudget):
        self._inner = inner
        self.budget = budget

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        if not self.budget.try_spend():
            raise BudgetExhausted("외부 LLM 의 오늘 호출 상한에 이르렀습니다.")
        return await self._inner.complete(
            prompt, system=system, max_tokens=max_tokens, json_mode=json_mode
        )
