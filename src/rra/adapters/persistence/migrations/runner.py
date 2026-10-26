"""번호 붙은 SQL 마이그레이션 적용기 — PRAGMA user_version + schema_version 표(적용 시각).

003 부터 schema_version 표가 있다. 표가 생기면 그 전에 적용된 버전도 행으로 채운다 (applied_at 은
채운 시각). 적용은 파일 순서대로, 각 파일 뒤 commit."""

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
        _record(conn, target)
        conn.commit()
        version = target
    return version


def _has_schema_version(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
    ).fetchone()
    return row is not None


def _record(conn: sqlite3.Connection, version: int) -> None:
    if not _has_schema_version(conn):
        return
    # 표가 막 생겼으면 그 전 버전들도 채운다 (user_version 만 있던 시절의 적용 이력)
    conn.executemany(
        "INSERT OR IGNORE INTO schema_version(version) VALUES (?)",
        [(v,) for v in range(1, version + 1)],
    )


def applied_versions(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    """schema_version 표의 (version, applied_at). 표가 없으면 빈 목록."""
    if not _has_schema_version(conn):
        return []
    rows = conn.execute("SELECT version, applied_at FROM schema_version ORDER BY version")
    return [(int(v), str(t)) for v, t in rows]
