"""AI 버튼 [취소] — 브라우저가 끊으면 작업을 멈춘다, 시간 제한은 없다 (ADR 0038)."""

from __future__ import annotations

import asyncio

import pytest

from rra.entrypoints.api.cancellable import ClientCancelled, cancel_on_disconnect


class _Req:
    def __init__(self, disconnect_after: float | None) -> None:
        self.disconnect_after = disconnect_after
        self.t0 = asyncio.get_running_loop().time()

    async def is_disconnected(self) -> bool:
        if self.disconnect_after is None:
            return False
        return asyncio.get_running_loop().time() - self.t0 >= self.disconnect_after


async def test_waits_without_time_limit_and_returns_result() -> None:
    async def slow() -> str:
        await asyncio.sleep(0.3)
        return "답"

    assert await cancel_on_disconnect(_Req(None), slow(), poll=0.05) == "답"


async def test_disconnect_cancels_work_before_it_writes() -> None:
    wrote: list[str] = []

    async def work() -> str:
        await asyncio.sleep(5)
        wrote.append("새 버전")  # 취소되면 여기까지 오지 않는다
        return "x"

    with pytest.raises(ClientCancelled):
        await cancel_on_disconnect(_Req(0.1), work(), poll=0.02)
    await asyncio.sleep(0)
    assert wrote == []


async def test_work_error_propagates() -> None:
    async def bad() -> None:
        raise ValueError("x")

    with pytest.raises(ValueError):
        await cancel_on_disconnect(_Req(None), bad(), poll=0.02)
