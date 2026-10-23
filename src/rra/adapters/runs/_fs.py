"""runs/ 파일 쓰기 공통 — 원자적 쓰기, 소유자 전용 권한 (보안 E·I: 디렉터리 700, 파일 600)."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any

DIR_MODE = 0o700
FILE_MODE = 0o600


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=DIR_MODE)
    os.chmod(path, DIR_MODE)  # umask 영향 제거
    return path


def write_json(path: Path, data: Any) -> None:
    """tmp → fsync → rename. 중간에 죽어도 이전 파일이 온전히 남는다."""
    body = json.dumps(data, ensure_ascii=False, indent=2, default=_default).encode("utf-8")
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, FILE_MODE)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def read_json(path: Path) -> Any:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as f:
        return json.loads(f.read())


def _default(value: Any) -> Any:
    if isinstance(value, set | frozenset):
        return sorted(value)
    raise TypeError(type(value).__name__)
