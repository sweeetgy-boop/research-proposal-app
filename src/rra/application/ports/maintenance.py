"""DB 유지보수 포트 — 재색인·백업. 구현은 adapters/persistence (SQLite)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DatabaseMaintenancePort(Protocol):
    async def reindex(self) -> dict[str, Any]:
        """모든 청크를 현재 임베딩 모델로 다시 색인. {"chunks", "dim", "model"}."""
        ...

    async def backup(self, out: str | Path) -> Path:
        """일관된 DB 사본을 out 에 만든다 (덮어쓰지 않음). 만든 경로."""
        ...
