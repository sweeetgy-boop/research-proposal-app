"""PRAGMA user_version 기반 마이그레이션 적용기."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

_MIGRATION_RE = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")
MIGRATIONS_DIR = Path(__file__).parent


def discover(directory: Path = MIGRATIONS_DIR) -> list[tuple[int, Path]]:
    found: list[tuple[int, Path]] = []
    for path in sorted(directory.glob("*.sql")):
        m = _MIGRATION_RE.match(path.name)
        if not m:
            raise ValueError(f"migration 파일명 규칙 위반: {path.name}")
        found.append((int(m.group(1)), path))
    versions = [v for v, _ in found]
    if versions != sorted(set(versions)):
        raise ValueError("migration 버전이 중복되거나 순서가 어긋납니다")
    return found


def current_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def migrate(conn: sqlite3.Connection, directory: Path = MIGRATIONS_DIR) -> int:
    """미적용 마이그레이션을 순서대로 적용하고 최종 버전을 반환."""
    version = current_version(conn)
    for target, path in discover(directory):
        if target <= version:
            continue
        conn.executescript(path.read_text(encoding="utf-8"))
        # PRAGMA 는 바인딩 파라미터를 지원하지 않는다. target 은 파일명에서 파싱한
        # 3자리 정수이므로 사용자 입력이 아니며 인젝션 경로가 없다.
        conn.execute(f"PRAGMA user_version = {int(target)}")  # noqa: S608
        conn.commit()
        version = target
    return version
