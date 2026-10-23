"""AsyncioTaskRunner — TaskRunner 포트의 asyncio 구현. 루프 안에서만 submit 할 수 있다."""

import asyncio

import pytest

from rra.adapters.runs import AsyncioTaskRunner
from rra.application.ports import TaskRunner


async def test_submit_wait_and_done_cleanup():
    runner = AsyncioTaskRunner()
    assert isinstance(runner, TaskRunner)

    async def work():
        await asyncio.sleep(0.01)
        return 42

    runner.submit("a", work())
    assert runner.is_running("a") and len(runner) == 1
    assert await runner.wait("a") == 42
    assert not runner.is_running("a") and len(runner) == 0


async def test_duplicate_key_is_rejected_and_coroutine_closed():
    runner = AsyncioTaskRunner()

    async def forever():
        await asyncio.sleep(3600)

    runner.submit("a", forever())
    with pytest.raises(ValueError, match="이미 실행 중"):
        runner.submit("a", forever())  # 두 번째 코루틴은 닫혀서 'never awaited' 경고가 없다
    assert runner.cancel("a")
    with pytest.raises(asyncio.CancelledError):
        await runner.wait("a")
    assert not runner.is_running("a")


async def test_cancel_and_wait_on_unknown_keys():
    runner = AsyncioTaskRunner()
    assert runner.cancel("nope") is False
    with pytest.raises(KeyError):
        await runner.wait("nope")


async def test_failure_propagates_through_wait_and_clears():
    runner = AsyncioTaskRunner()

    async def boom():
        raise RuntimeError("x")

    runner.submit("a", boom())
    with pytest.raises(RuntimeError):
        await runner.wait("a")
    assert not runner.is_running("a")


def test_submit_outside_a_loop_is_an_error():
    runner = AsyncioTaskRunner()

    async def noop():
        return None

    coro = noop()
    with pytest.raises(RuntimeError):
        runner.submit("a", coro)
    coro.close()
