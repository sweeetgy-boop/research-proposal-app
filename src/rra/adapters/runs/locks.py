"""프로세스 간 락 — fcntl.flock.

- 잡은 프로세스가 죽으면 커널이 풀어 준다 → "락이 비어 있음" = 실행하던 프로세스가 없음.
- 대기는 LOCK_NB 를 짧은 간격으로 다시 시도한다 (이벤트 루프를 막지 않는다).
- flock 은 열린 파일 설명자 단위라 같은 프로세스의 다른 fd 끼리도 배타적이다.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import os
from collections.abc import AsyncIterator
from pathlib import Path

from rra.adapters.runs._fs import FILE_MODE, ensure_dir

POLL_SEC = 0.5


def _open(path: Path) -> int:
    ensure_dir(path.parent)
    return os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, FILE_MODE)


def try_lock(path: Path) -> int | None:
    """잡으면 fd, 이미 잡혀 있으면 None."""
    fd = _open(path)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


def unlock(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def is_locked(path: Path) -> bool:
    if not path.exists():
        return False
    fd = try_lock(path)
    if fd is None:
        return True
    unlock(fd)
    return False


class FileLockClaim:
    """RunClaim 구현. release 는 여러 번 불러도 안전하다."""

    def __init__(self, fd: int):
        self._fd: int | None = fd

    def release(self) -> None:
        if self._fd is not None:
            fd, self._fd = self._fd, None
            unlock(fd)


class FlockSlot:
    """GenerationSlot 구현 — runs/.generate.lock. CLI·MCP 서버 등 모든 프로세스가 공유."""

    def __init__(self, path: Path, *, poll_sec: float = POLL_SEC):
        self.path = Path(path)
        self.poll_sec = poll_sec

    def __repr__(self) -> str:
        return "FlockSlot()"

    @contextlib.asynccontextmanager
    async def acquire(self) -> AsyncIterator[None]:
        while (fd := try_lock(self.path)) is None:
            await asyncio.sleep(self.poll_sec)
        try:
            yield
        finally:
            unlock(fd)
