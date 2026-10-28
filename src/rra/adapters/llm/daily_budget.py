"""외부 LLM 일일 전체 호출 상한 (레인 A) — 파일 카운터 + LLM 래퍼.

- FileDailyBudget: `<path>` JSON {"date": "YYYY-MM-DD", "count": n}. 날짜가 바뀌면 0 부터.
  프로세스 간(API·CLI·MCP) 같은 파일을 보며, 쓰기는 스레드 락 + 원자적 교체.
- BudgetedLLM: LLMPort 를 감싸 호출마다 try_spend(). 상한이면 BudgetExhausted — 호출하지 않는다.
  호출마다 응답 시간을 카운터 옆 `<카운터 이름>.latency.jsonl` 에 한 줄씩 남긴다
  (2026-10-28 밤, Argon 응답 시간 분포용) — 시각·단계·초·성공 여부·오류 종류만,
  프롬프트·응답 본문은 남기지 않는다(보안 D).
"""

from __future__ import annotations

import json
import threading
import time
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


_LATENCY_LOCK = threading.Lock()


def latency_path(budget: FileDailyBudget) -> Path:
    return budget.path.with_name(f"{budget.path.stem}.latency.jsonl")


def _log_latency(path: Path, stage: str, seconds: float, error: str | None) -> None:
    row = {
        "ts": datetime.now(UTC).astimezone().isoformat(timespec="seconds"),
        "stage": stage,
        "seconds": round(seconds, 2),
        "ok": error is None,
        "error": error,
    }
    try:
        with _LATENCY_LOCK:
            ensure_dir(path.parent)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass  # 기록 실패가 호출을 막지 않는다


class BudgetedLLM:
    """LLMPort 래퍼 — 호출 전에 예산을 쓴다. 그 밖의 속성(aclose·list_models)은 안쪽으로 위임."""

    def __init__(self, inner: Any, budget: FileDailyBudget, *, stage: str = ""):
        self._inner = inner
        self.budget = budget
        self.stage = stage

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
        t0 = time.perf_counter()
        error: str | None = None
        try:
            return await self._inner.complete(
                prompt, system=system, max_tokens=max_tokens, json_mode=json_mode
            )
        except BaseException as exc:  # 취소(CancelledError)도 기록한다
            error = type(exc).__name__
            raise
        finally:
            _log_latency(latency_path(self.budget), self.stage, time.perf_counter() - t0, error)
