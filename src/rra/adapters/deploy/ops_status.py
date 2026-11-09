"""OpsStatusPort·OpsStatusWriterPort 구현 — 운영 상태 파일 (계약 docs/contracts/healthz-status.md).

`<data_dir>/cache/ops_status.json` = {"tunnel": {state, since, checked_at}, "llm_local": {...}},
권한 600(runs/_fs.write_json: tmp → fsync → rename). 열거값·시각만 — 명령 출력 원문·IP·이름 없음.
쓰는 쪽은 `rra ops check`(launchd 5분)·`rra llm-check`, 읽는 쪽은 `/healthz`(명령 실행 없음).
기록 실패는 삼킨다 — 점검이 실패했다고 CLI 가 죽지 않게.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rra.adapters.runs._fs import ensure_dir, read_json, write_json
from rra.domain.rules import ops_status

logger = logging.getLogger("rra.ops")


def _now() -> datetime:
    return datetime.now(UTC).astimezone()


class FileOpsStatus:
    def __init__(self, path: Path, *, now: Callable[[], datetime] = _now):
        self.path = Path(path)
        self._now = now
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return f"FileOpsStatus({self.path})"

    def _read_all(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            data = read_json(self.path)
        except (ValueError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    # ── OpsStatusPort ──────────────────────────────────────
    def snapshot(self) -> Mapping[str, Any] | None:
        with self._lock:
            data = self._read_all()
        return dict(data) if data else None

    # ── OpsStatusWriterPort ────────────────────────────────
    def record(self, kind: str, state: str) -> None:
        if kind not in ops_status.KINDS or state not in ops_status.KINDS[kind]:
            return
        now = self._now().isoformat(timespec="seconds")
        try:
            with self._lock:
                data = self._read_all()
                prev = data.get(kind) if isinstance(data.get(kind), dict) else {}
                data[kind] = ops_status.advance(prev, state, now)
                ensure_dir(self.path.parent)
                write_json(self.path, data)
        except OSError as exc:  # 기록 실패가 점검을 막지 않는다
            logger.debug("ops.status_write_failed err=%s", type(exc).__name__)
