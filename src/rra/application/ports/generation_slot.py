from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol


class GenerationSlot(Protocol):
    """전역 생성 동시성 1 (프로세스 간). CLI 와 MCP 서버가 같은 슬롯을 나눠 쓴다."""

    def acquire(self) -> AbstractAsyncContextManager[None]: ...
