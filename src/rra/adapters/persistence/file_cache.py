"""파일 JSON 캐시 (CachePort) — data/cache/<name>/<sha256(key)>.json, ttl 지나면 없는 것으로.

키는 해시로만 파일명이 되고(경로 조작 불가), 값은 JSON 직렬화 가능한 것만. 비밀을 넣지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


class FileCache:
    def __init__(self, root: Path, *, ttl_sec: float = 7 * 24 * 3600, clock=time.time):
        self.root = Path(root)
        self.ttl_sec = ttl_sec
        self._clock = clock

    def _path(self, key: str) -> Path:
        return self.root / f"{hashlib.sha256(key.encode('utf-8')).hexdigest()}.json"

    def get(self, key: str) -> Any | None:
        path = self._path(key)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or self._clock() - float(data.get("at", 0)) > self.ttl_sec:
            return None
        return data.get("value")

    def set(self, key: str, value: Any) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self._path(key).with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"at": self._clock(), "value": value}, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(self._path(key))
