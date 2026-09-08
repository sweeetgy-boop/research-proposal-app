"""벡터 검색 백엔드 2종.

- `SqliteVecBackend`: sqlite-vec 확장(vec0) 사용. 확장 로드는 이 모듈에서만 하고
  로드 직후 `enable_load_extension(False)` 로 되돌린다.
- `BruteForceBackend`: 확장 없이 float32 BLOB + 파이썬 코사인. 개발·테스트·폴백용.

두 백엔드 모두 L2 정규화된 벡터를 저장하고 코사인 유사도 [0,1] 를 돌려준다.
"""

from __future__ import annotations

import math
import sqlite3
import struct
from typing import Protocol

MAX_DIM = 4096


def normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0.0:
        return [0.0] * len(vector)
    return [v / norm for v in vector]


def pack(vector: list[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def unpack(blob: bytes) -> list[float]:
    return list(struct.unpack(f"<{len(blob) // 4}f", blob))


def cosine(a: list[float], b: list[float]) -> float:
    """정규화된 벡터 전제. 영벡터는 0."""
    return max(0.0, min(1.0, sum(x * y for x, y in zip(a, b, strict=True))))


def validate_dim(dim: int) -> int:
    if not isinstance(dim, int) or isinstance(dim, bool) or not 1 <= dim <= MAX_DIM:
        raise ValueError(f"invalid embedding dim: {dim!r}")
    return dim


class VectorBackend(Protocol):
    name: str

    def create(self, dim: int) -> None: ...
    def add(self, rows: list[tuple[int, list[float]]]) -> None: ...
    def delete(self, chunk_rowids: list[int]) -> None: ...
    def search(self, vector: list[float], k: int) -> list[tuple[int, float]]: ...


class BruteForceBackend:
    """전 청크 선형 스캔. 수만 청크까지는 충분히 빠르다."""

    name = "bruteforce"

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, dim: int) -> None:
        validate_dim(dim)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS chunk_embeddings ("
            " chunk_rowid INTEGER PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,"
            " vec BLOB NOT NULL)"
        )

    def add(self, rows: list[tuple[int, list[float]]]) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO chunk_embeddings(chunk_rowid, vec) VALUES (?, ?)",
            [(rowid, pack(normalize(vec))) for rowid, vec in rows],
        )

    def delete(self, chunk_rowids: list[int]) -> None:
        self.conn.executemany(
            "DELETE FROM chunk_embeddings WHERE chunk_rowid = ?", [(r,) for r in chunk_rowids]
        )

    def search(self, vector: list[float], k: int) -> list[tuple[int, float]]:
        query = normalize(vector)
        scored = [
            (row[0], cosine(query, unpack(row[1])))
            for row in self.conn.execute("SELECT chunk_rowid, vec FROM chunk_embeddings")
        ]
        scored.sort(key=lambda rs: (-rs[1], rs[0]))
        return scored[:k]


class SqliteVecBackend:
    """sqlite-vec vec0 가상 테이블."""

    name = "sqlite-vec"

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    @classmethod
    def try_load(cls, conn: sqlite3.Connection) -> SqliteVecBackend | None:
        try:
            import sqlite_vec
        except ImportError:
            return None
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
        except (AttributeError, sqlite3.OperationalError, sqlite3.NotSupportedError):
            return None
        finally:
            # 확장 로드 창을 최소화한다: 이후 임의 확장 로드를 막는다.
            try:
                conn.enable_load_extension(False)
            except AttributeError:  # pragma: no cover - 빌드에 따라 없을 수 있음
                pass
        return cls(conn)

    def create(self, dim: int) -> None:
        # dim 은 validate_dim 을 통과한 정수. 사용자 문자열이 아니며 vec0 는
        # 차원을 바인딩 파라미터로 받지 못한다.
        ddl = (
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vec USING vec0("
            "chunk_rowid INTEGER PRIMARY KEY, "
            f"embedding float[{validate_dim(dim)}] distance_metric=cosine)"  # noqa: S608
        )
        self.conn.execute(ddl)

    def add(self, rows: list[tuple[int, list[float]]]) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO chunk_vec(chunk_rowid, embedding) VALUES (?, ?)",
            [(rowid, pack(normalize(vec))) for rowid, vec in rows],
        )

    def delete(self, chunk_rowids: list[int]) -> None:
        self.conn.executemany(
            "DELETE FROM chunk_vec WHERE chunk_rowid = ?", [(r,) for r in chunk_rowids]
        )

    def search(self, vector: list[float], k: int) -> list[tuple[int, float]]:
        rows = self.conn.execute(
            "SELECT chunk_rowid, distance FROM chunk_vec "
            "WHERE embedding MATCH ? AND k = ? ORDER BY distance",
            (pack(normalize(vector)), k),
        ).fetchall()
        return [(row[0], max(0.0, min(1.0, 1.0 - row[1]))) for row in rows]


def select_backend(conn: sqlite3.Connection, *, prefer_extension: bool = True) -> VectorBackend:
    if prefer_extension:
        backend = SqliteVecBackend.try_load(conn)
        if backend is not None:
            return backend
    return BruteForceBackend(conn)
