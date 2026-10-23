from __future__ import annotations

from collections.abc import Coroutine
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TaskRunner(Protocol):
    """백그라운드 실행기 — RunManager 가 생성 작업을 띄우는 유일한 통로.

    application 은 asyncio.create_task 를 직접 부르지 않는다. 진입점(CLI·UI 워커·REST)이 저마다의
    루프에 맞는 구현을 조립에서 끼운다. key 는 run_id. 같은 key 를 두 번 submit 하면 ValueError.
    """

    def submit(self, key: str, coro: Coroutine[Any, Any, Any]) -> None:
        """코루틴을 백그라운드로 띄운다. 끝나면(성공·실패·취소) is_running 이 False 가 된다."""
        ...

    def cancel(self, key: str) -> bool:
        """실행 중이면 취소를 요청하고 True. 모르는 key 면 False."""
        ...

    def is_running(self, key: str) -> bool: ...

    async def wait(self, key: str) -> Any:
        """끝날 때까지 기다려 결과를 돌려준다. 취소됐으면 CancelledError, 모르는 key 면 KeyError."""
        ...
