"""자료원 가용 상태 파일 (SourceAvailabilityPort) — <data>/cache/source_availability.json (레인 I).

`{source: {"notice": 문구, "at": epoch}}`. IP 거부 같은 차단 안내를 적재(CLI)·사전 점검(API)·
`rra sources check` 가 적고, `GET /v1/sources/status` 가 읽어 웹 자료원 상태에 보인다.
비밀·본문은 넣지 않는다. 파일이 없거나 깨져 있으면 빈 상태.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

MAX_NOTICE_CHARS = 300
MAX_SOURCES = 64
_NAME = re.compile(r"^[a-z0-9_]{1,40}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class FileSourceAvailability:
    def __init__(self, path: Path, *, clock=time.time):
        self.path = Path(path)
        self._clock = clock

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def record(self, source: str, notice: str | None) -> None:
        if not _NAME.match(source):
            return
        data = self._load()
        if notice is None:
            if source in data:
                del data[source]
                self._save(data)
            return
        clean = " ".join(_CONTROL.sub(" ", notice).split())[:MAX_NOTICE_CHARS]
        if len(data) >= MAX_SOURCES and source not in data:
            return
        data[source] = {"notice": clean, "at": self._clock()}
        self._save(data)

    def notice(self, source: str) -> str | None:
        return self.notices().get(source)

    def notices(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for name, row in self._load().items():
            if _NAME.match(str(name)) and isinstance(row, dict) and row.get("notice"):
                out[str(name)] = str(row["notice"])[:MAX_NOTICE_CHARS]
        return out
