"""화면 스레드와 분리된 단일 워커 — 자체 이벤트 루프를 가진 데몬 스레드.

Streamlit 은 상호작용마다 스크립트를 다시 실행하고 이벤트 루프를 유지하지 않는다.
RunManager 는 TaskRunner 포트(조립: AsyncioTaskRunner)로 백그라운드 실행하므로 살아 있는 루프가
필요하다. 그래서 프로세스에 워커 하나를 두고(st.cache_resource), 조립과 모든 유스케이스 호출을
그 루프에서 돈다 — 실행기는 그 루프에 Task 를 만든다.
화면은 run_coroutine_threadsafe(...).result(timeout) 로 짧게 기다리기만 한다.

sqlite 연결·LLM 클라이언트는 만든 스레드/루프에 묶인다.
그래서 동기 호출(precheck·검색)도 루프에서 실행한다.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Coroutine
from typing import Any

from rra.application.services import ProposalAssistant

CALL_TIMEOUT = 120.0  # 임베딩 모델 첫 로드(precheck)·검색까지 포함
WAIT_TIMEOUT = 1800.0


class Worker:
    def __init__(self, factory: Callable[[], ProposalAssistant]):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="rra-ui-worker", daemon=True
        )
        self._thread.start()
        self.assistant: ProposalAssistant = self.call(_wrap(factory))

    def call[T](self, coro: Coroutine[Any, Any, T], *, timeout: float = CALL_TIMEOUT) -> T:
        """코루틴을 워커 루프에서 실행하고 결과를 기다린다."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def sync[T](
        self, fn: Callable[..., T], *args: Any, timeout: float = CALL_TIMEOUT, **kw: Any
    ) -> T:
        """동기 함수도 워커 스레드에서 실행한다 (sqlite 스레드 제약)."""
        return self.call(_wrap(fn, *args, **kw), timeout=timeout)

    def wait(self, run_id: str, *, timeout: float = WAIT_TIMEOUT):
        """run 이 끝날 때까지 기다린다 (테스트·점검용. 화면은 폴링한다)."""
        a = self.assistant
        return self.call(a.manager.wait(a.user, run_id), timeout=timeout)

    def close(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)


async def _wrap[T](fn: Callable[..., T], *args: Any, **kw: Any) -> T:
    return fn(*args, **kw)
