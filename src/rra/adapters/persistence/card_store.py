"""문제 정의 카드 재사용 저장소 (CachePort, 계약 problem-card.md 4.4절).

- `PrivateFileCache`: `FileCache` 와 같은 모양(파일 이름은 키의 sha256 뿐)에 폴더 700·파일 600.
  `ttl_sec=None` 이면 만료 없음(고정 카드).
- `MemoryCache`: 가짜 모드·시험용 — 데이터 폴더를 건드리지 않는다.

값은 카드 JSON 뿐이다. 입력 원문·사용자 식별값을 넣지 않는다(키는 해시).
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any

from rra.adapters.persistence.file_cache import FileCache


class PrivateFileCache(FileCache):
    def __init__(
        self, root: Path, *, ttl_sec: float | None, secure_parent: bool = False, clock=time.time
    ):
        super().__init__(root, ttl_sec=math.inf if ttl_sec is None else ttl_sec, clock=clock)
        self.secure_parent = secure_parent  # 하위 폴더(pinned/)면 바로 위 폴더도 700 으로

    def set(self, key: str, value: Any) -> None:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        if self.secure_parent:
            os.chmod(self.root.parent, 0o700)
        path = self._path(key)
        tmp = path.with_suffix(".tmp")
        body = json.dumps({"at": self._clock(), "value": value}, ensure_ascii=False)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.chmod(tmp, 0o600)
        tmp.replace(path)


class MemoryCache:
    def __init__(self) -> None:
        self._items: dict[str, Any] = {}

    def get(self, key: str) -> Any | None:
        value = self._items.get(key)
        return json.loads(value) if value is not None else None

    def set(self, key: str, value: Any) -> None:
        self._items[key] = json.dumps(value, ensure_ascii=False)
