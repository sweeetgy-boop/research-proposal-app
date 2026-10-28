"""AI 버튼 요청의 [취소] — 브라우저가 요청을 끊으면 그 작업만 멈춘다 (2026-10-28 밤, ADR 0038).

응답 시간 제한은 두지 않는다. 화면은 "응답 기다리는 중 · 경과 n초" 와 [취소] 를 보이고,
취소하면 fetch 를 abort 한다. 서버는 연결이 끊긴 것을 보고 작업(코루틴)을 취소한다 — 취소된
클릭이 끝까지 돌아 새 버전·파일을 쓰는 일이 없게. 끊김 확인은 `request.is_disconnected()` 를
짧은 간격으로 본다(본문은 이미 읽힌 뒤라 다음 수신은 http.disconnect 뿐이다).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable
from typing import Protocol

logger = logging.getLogger("rra.api.cancel")

POLL_SECONDS = 0.5
CANCELLED_STATUS = 499  # nginx 관례 "Client Closed Request" — 브라우저는 이미 떠났다


class ClientCancelled(Exception):
    """브라우저가 요청을 끊었다 — 작업을 멈췄다."""


class _Disconnectable(Protocol):
    async def is_disconnected(self) -> bool: ...


async def cancel_on_disconnect[T](
    request: _Disconnectable, work: Awaitable[T], *, poll: float = POLL_SECONDS
) -> T:
    """work 를 끝까지 기다린다(시간 제한 없음). 그사이 연결이 끊기면 work 를 취소하고
    ClientCancelled."""
    task = asyncio.ensure_future(work)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=poll)
            if done:
                return task.result()
            if await request.is_disconnected():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
                logger.info("api.cancel.client_disconnected")
                raise ClientCancelled
    except asyncio.CancelledError:  # 서버 종료 등 — 작업도 함께 멈춘다
        task.cancel()
        raise
