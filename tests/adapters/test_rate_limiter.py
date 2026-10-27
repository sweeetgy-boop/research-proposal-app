"""공용 호출 제한기 — 동시성·분당 상한·429 백오프를 가짜 시계로 검증. 실제 대기 없음."""

import asyncio

import httpx
import pytest

from rra.adapters.llm.errors import LLMError
from rra.adapters.llm.openai_compat import OpenAICompatLLM, RetryPolicy
from rra.adapters.llm.rate_limiter import (
    RateLimiter,
    limiter_for,
    parse_retry_after,
    reset_registry,
)


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
        await asyncio.sleep(0)


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_registry()
    yield
    reset_registry()


async def test_concurrency_is_capped_per_loop():
    clock = FakeClock()
    limiter = RateLimiter(concurrency=2, per_minute=0, clock=clock, sleep=clock.sleep)
    running, peak = 0, 0
    gate = asyncio.Event()

    async def worker():
        nonlocal running, peak
        async with limiter:
            running += 1
            peak = max(peak, running)
            await gate.wait()
            running -= 1

    tasks = [asyncio.create_task(worker()) for _ in range(5)]
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert peak == 2 and running == 2
    gate.set()
    await asyncio.gather(*tasks)
    assert peak == 2 and limiter.total_acquired == 5


async def test_per_minute_window_waits_until_oldest_start_expires():
    clock = FakeClock()
    limiter = RateLimiter(concurrency=10, per_minute=3, clock=clock, sleep=clock.sleep)
    for _ in range(3):
        await limiter.acquire()
        limiter.release()
        clock.now += 1.0  # 시작 시각 0, 1, 2
    await limiter.acquire()  # 4번째: 0 + 60 - 3 = 57초 대기
    limiter.release()
    assert clock.sleeps == [57.0] and clock.now == 60.0
    assert limiter.total_waits == 1


async def test_429_backoff_is_exponential_and_retry_after_wins():
    clock = FakeClock()
    limiter = RateLimiter(concurrency=1, per_minute=0, clock=clock, sleep=clock.sleep)
    assert limiter.note_429(None) == 1.0
    assert limiter.note_429(None) == 2.0
    assert limiter.note_429(None) == 4.0
    assert limiter.note_429(retry_after=30) == 30.0
    assert limiter.blocked_until == 30.0
    await limiter.acquire()  # 모든 호출자가 blocked_until 까지 기다린다
    limiter.release()
    assert clock.sleeps == [30.0]
    limiter.note_success()
    assert limiter.note_429(None) == 1.0  # 성공 뒤 되돌림
    assert limiter.note_429(retry_after=10_000) == 300.0  # 서버 값도 상한


def test_parse_retry_after_accepts_seconds_only():
    assert parse_retry_after("12") == 12.0 and parse_retry_after(" 0.5 ") == 0.5
    assert parse_retry_after("Wed, 21 Oct 2026 07:28:00 GMT") is None
    assert parse_retry_after("-3") is None and parse_retry_after(None) is None


def test_registry_shares_one_limiter_per_provider():
    a = limiter_for("gemini", concurrency=4, per_minute=60)
    b = limiter_for("Gemini", concurrency=1, per_minute=1)  # 두 번째 설정은 무시 — 같은 객체
    assert a is b and a.concurrency == 4
    assert limiter_for("openai") is not a


# ── OpenAICompatLLM 배선 ─────────────────────────────────
BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
ALLOWED = ["generativelanguage.googleapis.com"]


def ok(content="[]"):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


async def test_llm_honours_retry_after_on_429_and_shares_backoff():
    clock = FakeClock()
    limiter = RateLimiter(concurrency=4, per_minute=0, clock=clock, sleep=clock.sleep)
    responses = [httpx.Response(429, headers={"Retry-After": "7"}, text="slow down"), ok("done")]

    def handler(request):
        return responses.pop(0)

    llm = OpenAICompatLLM(
        BASE,
        "gemini-4-argon",
        provider="gemini",
        api_key="sk-test-not-real",
        allowed_hosts=ALLOWED,
        transport=httpx.MockTransport(handler),
        sleep=clock.sleep,
        retry=RetryPolicy(attempts=3, backoff_sec=0.5),
        limiter=limiter,
    )
    assert await llm.complete("hi") == "done"
    assert clock.sleeps == [7.0]  # 재시도 간격은 max(백오프 0.5, Retry-After 7)
    assert limiter.consecutive_429 == 0  # 성공 뒤 되돌림
    assert limiter.total_acquired == 2


async def test_llm_without_limiter_still_uses_retry_after():
    clock = FakeClock()
    responses = [httpx.Response(429, headers={"Retry-After": "3"}), ok("x")]
    llm = OpenAICompatLLM(
        "http://127.0.0.1:8080/v1",
        "m",
        transport=httpx.MockTransport(lambda r: responses.pop(0)),
        sleep=clock.sleep,
        retry=RetryPolicy(attempts=2, backoff_sec=0),
    )
    assert await llm.complete("hi") == "x" and clock.sleeps == [3.0]


async def test_exhausted_429_raises_after_backoffs():
    clock = FakeClock()
    limiter = RateLimiter(concurrency=4, per_minute=0, clock=clock, sleep=clock.sleep)
    llm = OpenAICompatLLM(
        BASE,
        "m",
        provider="gemini",
        api_key="sk-test-not-real",
        allowed_hosts=ALLOWED,
        transport=httpx.MockTransport(lambda r: httpx.Response(429, text="busy")),
        sleep=clock.sleep,
        retry=RetryPolicy(attempts=3, backoff_sec=0),
        limiter=limiter,
    )
    with pytest.raises(LLMError, match="429"):
        await llm.complete("hi")
    assert clock.sleeps == [1.0, 2.0] and limiter.consecutive_429 == 3
