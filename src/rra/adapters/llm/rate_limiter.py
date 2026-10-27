"""공용 호출 제한기 — provider 별 프로세스 내 공유 (Gemini 등 원격 LLM).

- 동시성: provider 당 최대 N 개 요청 (기본 4). 이벤트 루프마다 세마포어를 따로 둔다
  (Streamlit 워커 스레드처럼 루프가 여럿일 수 있다. 창·백오프 상태는 숫자라 루프와 무관하게 공유).
- 분당 상한: 최근 60초 안의 시작 시각을 세어 넘으면 가장 오래된 것이 창을 벗어날 때까지 기다린다.
- 429: `note_429(retry_after)` 가 지수 백오프(기본 1·2·4…초, 상한 60초)를 계산하고 Retry-After 가
있으면
  그 값을 우선한다. 그동안 모든 호출자가 `blocked_until` 까지 기다린다. 성공하면 연속 횟수를
  되돌린다.
- 프로세스 하나 안에서만 유효하다. 프로세스 간 제한(크롤·판독·검토를 동시에 돌릴 때)은 통합 세션의
  큐가 맡는다 — 이 제한기는 그 아래 2차 방어선.

레지스트리: `limiter_for(provider, concurrency=…, per_minute=…)` 는 provider 당 하나를 만들어
돌려준다.
같은 provider 로 만든 모든 LLM 인스턴스(검토·차별화·추천·판독)가 같은 제한기를 쓴다.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable

DEFAULT_CONCURRENCY = 4
DEFAULT_PER_MINUTE = 60
WINDOW_SEC = 60.0
BACKOFF_BASE_SEC = 1.0
BACKOFF_MAX_SEC = 60.0
MAX_RETRY_AFTER_SEC = 300.0  # 서버가 준 Retry-After 도 이 위로는 믿지 않는다


class RateLimiter:
    def __init__(
        self,
        *,
        concurrency: int = DEFAULT_CONCURRENCY,
        per_minute: int = DEFAULT_PER_MINUTE,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        backoff_base_sec: float = BACKOFF_BASE_SEC,
        backoff_max_sec: float = BACKOFF_MAX_SEC,
    ):
        self.concurrency = max(1, int(concurrency))
        self.per_minute = max(0, int(per_minute))  # 0 = 분당 상한 없음
        self._clock, self._sleep = clock, sleep
        self.backoff_base_sec, self.backoff_max_sec = backoff_base_sec, backoff_max_sec
        self._sems: dict[int, asyncio.Semaphore] = {}
        self._starts: deque[float] = deque()
        self.blocked_until = 0.0
        self.consecutive_429 = 0
        self.total_acquired = 0
        self.total_waits = 0

    def __repr__(self) -> str:
        return f"RateLimiter(concurrency={self.concurrency}, per_minute={self.per_minute})"

    # ── 획득·해제 ─────────────────────────────────────────
    def _sem(self) -> asyncio.Semaphore:
        key = id(asyncio.get_running_loop())
        sem = self._sems.get(key)
        if sem is None:
            sem = self._sems[key] = asyncio.Semaphore(self.concurrency)
        return sem

    async def acquire(self) -> None:
        sem = self._sem()
        await sem.acquire()
        try:
            await self._wait_turn()
        except BaseException:
            sem.release()
            raise
        self._starts.append(self._clock())
        self.total_acquired += 1

    def release(self) -> None:
        sem = self._sems.get(id(asyncio.get_running_loop()))
        if sem is not None:
            sem.release()

    async def __aenter__(self) -> RateLimiter:
        await self.acquire()
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.release()

    async def _wait_turn(self) -> None:
        while True:
            now = self._clock()
            delay = max(0.0, self.blocked_until - now)
            if self.per_minute:
                while self._starts and now - self._starts[0] >= WINDOW_SEC:
                    self._starts.popleft()
                if len(self._starts) >= self.per_minute:
                    delay = max(delay, self._starts[0] + WINDOW_SEC - now)
            if delay <= 0:
                return
            self.total_waits += 1
            await self._sleep(delay)

    # ── 429 백오프 ────────────────────────────────────────
    def note_429(self, retry_after: float | None = None) -> float:
        """다음 시도까지 기다릴 초. 모든 호출자가 그때까지 멈춘다."""
        self.consecutive_429 += 1
        backoff = min(
            self.backoff_max_sec, self.backoff_base_sec * (2 ** (self.consecutive_429 - 1))
        )
        if retry_after is not None and retry_after > 0:
            delay = min(MAX_RETRY_AFTER_SEC, float(retry_after))
        else:
            delay = backoff
        self.blocked_until = max(self.blocked_until, self._clock() + delay)
        return delay

    def note_success(self) -> None:
        self.consecutive_429 = 0


def parse_retry_after(value: str | None) -> float | None:
    """Retry-After 헤더: 초(정수·소수)만 받는다. HTTP-date 형식은 무시(None → 지수 백오프)."""
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


# ── provider 별 레지스트리 (프로세스 내) ───────────────────
_REGISTRY: dict[str, RateLimiter] = {}


def limiter_for(
    provider: str,
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
    per_minute: int = DEFAULT_PER_MINUTE,
    **kw: object,
) -> RateLimiter:
    key = provider.strip().lower()
    limiter = _REGISTRY.get(key)
    if limiter is None:
        limiter = _REGISTRY[key] = RateLimiter(
            concurrency=concurrency,
            per_minute=per_minute,
            **kw,  # type: ignore[arg-type]
        )
    return limiter


def reset_registry() -> None:
    """테스트 전용."""
    _REGISTRY.clear()
