"""TaskRunner 구현 — 호출 시점의 asyncio 루프에 Task 를 만든다.

CLI(asyncio.run)·UI 워커(전용 루프 스레드)·REST(uvicorn 루프) 모두 같은 구현을 쓴다.
submit 은 반드시 돌고 있는 루프 안(코루틴 안)에서 불러야 한다.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any


class AsyncioTaskRunner:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    def submit(self, key: str, coro: Coroutine[Any, Any, Any]) -> None:
        if key in self._tasks:
            coro.close()
            raise ValueError(f"이미 실행 중인 작업입니다: {key}")
        task = asyncio.get_running_loop().create_task(coro, name=f"rra-run-{key}")
        self._tasks[key] = task
        task.add_done_callback(lambda _t, k=key: self._tasks.pop(k, None))

    def cancel(self, key: str) -> bool:
        task = self._tasks.get(key)
        if task is None:
            return False
        return task.cancel()

    def is_running(self, key: str) -> bool:
        return key in self._tasks

    async def wait(self, key: str) -> Any:
        task = self._tasks.get(key)
        if task is None:
            raise KeyError(key)
        return await task

    def __len__(self) -> int:
        return len(self._tasks)
