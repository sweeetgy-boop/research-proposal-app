"""DB 유지보수 유스케이스 — 재색인(`rra reindex`)·백업(`rra db backup`).

백업 보관: 같은 폴더의 `<stem>-YYYYMMDD-HHMMSS.sqlite` 중 최신 keep 벌만 남기고 나머지를 지운다.
지우는 대상은 자기 이름 규칙에 맞는 파일, 그리고 방금 만든 사본과 같은 폴더 안에서만.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from rra.application.ports.maintenance import DatabaseMaintenancePort

_STAMP = re.compile(r"^(?P<stem>.+)-\d{8}-\d{6}\.sqlite$")


@dataclass(frozen=True)
class BackupReport:
    path: Path
    kept: list[Path] = field(default_factory=list)
    removed: list[Path] = field(default_factory=list)


class ReindexDocuments:
    def __init__(self, db: DatabaseMaintenancePort):
        self.db = db

    async def __call__(self) -> dict[str, Any]:
        return await self.db.reindex()


class BackupDatabase:
    """out 이 디렉터리(또는 .sqlite 가 아닌 경로)면 `rra-YYYYMMDD-HHMMSS.sqlite` 이름을 붙인다."""

    def __init__(
        self, db: DatabaseMaintenancePort, *, clock: Callable[[], datetime] = datetime.now
    ):
        self.db = db
        self.clock = clock

    async def __call__(self, out: str | Path, *, keep: int = 7, stem: str = "rra") -> BackupReport:
        target = Path(out)
        if target.suffix != ".sqlite":
            target = target / f"{stem}-{self.clock():%Y%m%d-%H%M%S}.sqlite"
        path = await self.db.backup(target)
        m = _STAMP.match(path.name)
        if m is None or keep <= 0:
            return BackupReport(path=path)
        family = sorted(
            (
                p
                for p in path.parent.glob(f"{m.group('stem')}-*.sqlite")
                if _STAMP.match(p.name) and p.is_file()
            ),
            key=lambda p: p.name,
        )
        removed = family[:-keep] if len(family) > keep else []
        for old in removed:
            old.unlink()
        return BackupReport(
            path=path, kept=[p for p in family if p not in removed], removed=removed
        )
