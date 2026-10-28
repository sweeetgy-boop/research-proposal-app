"""DocumentRepository 구현 — SQLite FTS5 + 벡터, RRF 하이브리드.

포트는 비동기다. 임베딩은 EmbeddingPort(비동기) 에 맡기고, SQLite 접근은 asyncio.to_thread 로
돌린다. 연결은 check_same_thread=False 로 열고 RLock 으로 직렬화한다 (스레드풀 어느 스레드든 1개씩).

보안 E:
- 모든 SQL 은 모듈 상수. 사용자 문자열은 항상 바인딩 파라미터로만 들어간다.
- FTS5 MATCH 식은 `_sql.quote_fts_query()` 를 거친 것만 사용한다.
- k·질의 길이·질의 개수 상한을 강제한다.
- DB 파일 0o600, 상위 디렉터리 0o700 로 고정한다.

[2] DB 정비 (2026-10-26):
- 마이그레이션 001~003 (migrations/runner, user_version + schema_version 표).
- documents.valid_until 이 지난 문서는 검색(FTS·벡터)·precheck(find_similar) 에서 제외한다. 기준일은
  today() (테스트에서 바꿀 수 있다).
- meta.embedding_model 에 색인에 쓴 임베딩 모델명을 적고, 설정 모델과 다르면 기동 때 경고 로그 +
  index_model_mismatch. `rra reindex`(reindex()) 가 모든 청크를 현재 모델로 다시 임베딩한다.
- backup(out) 은 VACUUM INTO 로 일관된 사본을 만든다 (권한 0600).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rra.adapters.persistence import _mapping, _sql, _vec
from rra.adapters.persistence.migrations import runner
from rra.domain.models import Chunk, Document, TableFact
from rra.domain.rules.fusion import DEFAULT_K as RRF_K
from rra.domain.rules.fusion import reciprocal_rank_fusion
from rra.domain.rules.live_search import match_existing, normalized_title

if TYPE_CHECKING:  # 포트는 구조적 타입 — 런타임 의존 없음
    from rra.application.ports.embedding import EmbeddingPort

logger = logging.getLogger("rra.persistence")

DB_FILE_MODE = 0o600
DB_DIR_MODE = 0o700
FETCH_MULTIPLIER = 4
REINDEX_BATCH = 64
# 만료 문서 제외 조건 — 바인딩 하나(기준일 ISO). d 는 documents 별칭.
_VALID = "(d.valid_until IS NULL OR d.valid_until >= ?)"

# 컬럼 이름은 _mapping.DOCUMENT_COLUMNS 상수에서만 오고 값은 전부 바인딩된다.
_INSERT_DOCUMENT = (
    "INSERT INTO documents ("  # noqa: S608  # nosec B608 - 컬럼명은 상수, 값은 바인딩
    + ",".join(_mapping.DOCUMENT_COLUMNS)
    + ") VALUES ("  # nosec B608
    + _sql.placeholders(len(_mapping.DOCUMENT_COLUMNS))
    + ") ON CONFLICT(doc_id) DO UPDATE SET "  # nosec B608
    + ",".join(f"{c}=excluded.{c}" for c in _mapping.DOCUMENT_COLUMNS if c != "doc_id")
    + ", ingested_at=strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"
)
_TOUCH_INGESTED = (
    "UPDATE documents SET ingested_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE doc_id = ?"
)
_SOURCE_STATUS = "SELECT source, COUNT(*), MAX(ingested_at) FROM documents GROUP BY source"
_INSERT_CHUNK = "INSERT INTO chunks (chunk_id, doc_id, ordinal, heading, text) VALUES (?,?,?,?,?)"
_SELECT_DOCUMENT = "SELECT * FROM documents WHERE doc_id = ?"
# FTS5 는 MATCH·bm25() 에서 별칭이 아니라 테이블 이름을 요구한다.
# {valid} 는 모듈 상수 _VALID(바인딩 하나), {orgs} 는 placeholders(정수 개수) 로만 채워진다.
_FTS_SEARCH = (
    "SELECT c.chunk_id FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid "
    "JOIN documents d ON d.doc_id = c.doc_id "
    "WHERE chunks_fts MATCH ? AND {valid} ORDER BY bm25(chunks_fts), c.id LIMIT ?"
).replace("{valid}", _VALID)
# {orgs}·{sources} 는 placeholders(정수 개수) 로만 채워진다 (_fts_ids).
_FTS_SEARCH_FILTERED = (
    "SELECT c.chunk_id FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid "
    "JOIN documents d ON d.doc_id = c.doc_id "
    "WHERE chunks_fts MATCH ? AND {valid}{filters} "
    "ORDER BY bm25(chunks_fts), c.id LIMIT ?"
).replace("{valid}", _VALID)
_ORG_FILTER = (
    " AND EXISTS (SELECT 1 FROM document_orgs o WHERE o.doc_id = c.doc_id AND o.org IN ({orgs}))"
)
_SOURCE_FILTER = " AND d.source IN ({sources})"
# find_similar(sources=…) 의 벡터 사전 필터 — 자료원에 속한 청크 rowid 부분집합 (값은 바인딩,
# ADR 0028)
_ROWIDS_OF_SOURCES = (
    "SELECT c.id FROM chunks c JOIN documents d ON d.doc_id = c.doc_id "
    "WHERE d.source IN ({sources})"
)
# 필터(orgs·sources)가 있으면 벡터 상위 목록을 필터 뒤에 다시 채워야 한다. 한국어 사내 기록이 상위를
# 메우면(2026-10-26 골든셋 01: 상위 160 중 영어 논문 4) 자료원 하나를 고르려고 훨씬 더 받아야 하므로
# 부족하면 4배씩 늘려 다시 받는다. 상한은 DoS 방지.
VEC_FETCH_CAP = 4096
_SELECT_ALL_CHUNKS = "SELECT id, text FROM chunks ORDER BY id"
# P2-8 표 사실 (migration 005). 값은 전부 바인딩, LIKE 패턴은 _like_pattern 으로 이스케이프.
_FACT_COLUMNS = (
    "doc_id, item, year, unit, value, value_text, page, sheet, row_label, col_label, basis"
)
_INSERT_FACT = f"INSERT INTO table_facts ({_FACT_COLUMNS}) VALUES ({_sql.placeholders(11)})"  # noqa: S608  # nosec B608 - 상수
_DELETE_FACTS = "DELETE FROM table_facts WHERE doc_id = ?"
_SELECT_FACTS = f"SELECT {_FACT_COLUMNS} FROM table_facts"  # noqa: S608  # nosec B608 - 상수
_FACT_COUNTS = (
    "SELECT substr(doc_id, 1, instr(doc_id, ':') - 1) AS src, COUNT(*) FROM table_facts "
    "GROUP BY src"
)
MAX_FACT_TOKENS = 8
_SAMPLE_SOURCES = "SELECT DISTINCT source FROM documents ORDER BY source"
_SAMPLE_CHUNKS = (
    "SELECT c.chunk_id, c.doc_id, c.ordinal, c.heading, c.text, "
    "d.text_basis AS basis, d.visibility AS visibility "
    "FROM chunks c JOIN documents d ON d.doc_id = c.doc_id WHERE d.source = ? "
    "ORDER BY c.id LIMIT ?"
)
_DOCUMENTS_OF = "SELECT * FROM documents WHERE source = ? ORDER BY doc_id LIMIT ?"
# [4] 실시간 결과의 동일성 조회 (find_identities). {marks} 는 placeholders(정수 개수) 로만 채운다.
_BY_DOI = "SELECT * FROM documents WHERE doi IN ({marks})"
_BY_APPNO = "SELECT * FROM documents WHERE application_no IN ({marks})"
_BY_PROJECT_NO = (
    "SELECT * FROM documents WHERE doc_type IN ('report', 'internal_report') "
    "AND json_extract(raw_json, '$.project_no') IN ({marks})"
)
# rra_norm_title 은 연결에 등록한 파이썬 함수 (domain/rules/live_search.normalized_title)
_BY_NORM_TITLE = "SELECT * FROM documents WHERE rra_norm_title(title) IN ({marks})"
MAX_IDENTITY_DOCS = 150  # dois 는 2배까지 — placeholders 상한(MAX_K×4) 안


@dataclass(frozen=True)
class _Filter:
    """hybrid_search 의 선택 필터. sql() 은 자리표시자만, 값은 params() 로 바인딩 (보안 E)."""

    orgs: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.orgs or self.sources)

    def sql(self) -> str:
        out = ""
        if self.orgs:
            out += _ORG_FILTER.replace("{orgs}", _sql.placeholders(len(self.orgs)))
        if self.sources:
            out += _SOURCE_FILTER.replace("{sources}", _sql.placeholders(len(self.sources)))
        return out

    def params(self) -> tuple[str, ...]:
        return (*self.orgs, *self.sources)


class ReindexRequired(RuntimeError):
    """기존 색인과 임베딩 차원·백엔드가 달라 재색인이 필요할 때."""


def _norm_title_sql(title: Any) -> str:
    return normalized_title(title) if isinstance(title, str) else ""


def _secure_paths(db_path: Path) -> None:
    """E. 소유자 전용 권한 강제. (Windows 는 POSIX 모드 비트가 없어 건너뜀)"""
    if os.name == "nt":
        return
    parent = db_path.parent
    if parent.exists():
        os.chmod(parent, DB_DIR_MODE)
    for path in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
        if path.exists():
            os.chmod(path, DB_FILE_MODE)


class SQLiteDocumentRepository:
    def __init__(
        self,
        db_path: str | Path,
        embedding: EmbeddingPort,
        *,
        max_k: int = _sql.MAX_K,
        max_queries: int = _sql.MAX_QUERIES,
        max_query_chars: int = _sql.MAX_QUERY_CHARS,
        prefer_extension: bool = True,
        rrf_k: int = RRF_K,
        min_similarity: float = 0.0,
        today: Callable[[], date] = date.today,
    ):
        self.db_path = Path(db_path)
        self.embedding = embedding
        self.today = today
        self.max_k = max_k
        self.max_queries = max_queries
        self.max_query_chars = max_query_chars
        self.rrf_k = rrf_k
        # 코사인 유사도가 이 값 이하인 청크는 벡터 랭킹에서 제외한다.
        # (벡터 검색은 거리와 무관하게 상위 k 개를 돌려주므로, 이 필터가 없으면
        #  아무 신호도 없는 청크가 RRF 결과에 섞인다)
        self.min_similarity = min_similarity

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        _secure_paths(self.db_path)
        self._lock = threading.RLock()
        self._query_memo: tuple[str, list[float]] | None = None  # 마지막 질의 임베딩 (find_similar)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._configure()
        runner.migrate(self.conn)
        self.backend = self._select_backend(prefer_extension)
        self._vec_dim = self._stored_dim()
        self.index_model: str | None = self._get_meta("embedding_model")  # 색인에 쓴 모델
        if self.index_model_mismatch:
            logger.warning(
                "db.embedding_model_mismatch index=%s configured=%s — `rra reindex` 필요",
                self.index_model,
                self.configured_model,
            )
        _secure_paths(self.db_path)

    @property
    def configured_model(self) -> str | None:
        """설정된 임베딩 모델명 (어댑터가 model_name 을 노출할 때만)."""
        name = getattr(self.embedding, "model_name", None)
        return str(name) if name else None

    @property
    def index_model_mismatch(self) -> bool:
        return bool(
            self.index_model and self.configured_model and self.index_model != self.configured_model
        )

    @property
    def schema_version(self) -> int:
        return runner.current_version(self.conn)

    # ── 연결·설정 ────────────────────────────────────────────────
    def _configure(self) -> None:
        # [4] 제목 정규화 함수 — 질의에서만 쓴다 (스키마·트리거에는 쓰지 않는다, trusted_schema OFF)
        self.conn.create_function("rra_norm_title", 1, _norm_title_sql, deterministic=True)
        self.conn.execute("PRAGMA trusted_schema = OFF")  # 악성 스키마 방어
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA busy_timeout = 5000")

    def _select_backend(self, prefer_extension: bool) -> _vec.VectorBackend:
        pinned = self._get_meta("vec_backend")
        if pinned == _vec.BruteForceBackend.name:
            return _vec.BruteForceBackend(self.conn)
        if pinned == _vec.SqliteVecBackend.name:
            backend = _vec.SqliteVecBackend.try_load(self.conn)
            if backend is None:
                raise ReindexRequired(
                    "이 DB 는 sqlite-vec 로 색인되었습니다. "
                    "sqlite-vec 를 설치하거나 DB 를 재색인하세요."
                )
            return backend
        return _vec.select_backend(self.conn, prefer_extension=prefer_extension)

    def _get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def _set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def _stored_dim(self) -> int | None:
        raw = self._get_meta("embedding_dim")
        return int(raw) if raw is not None else None

    def _ensure_vec_table(self) -> None:
        dim = _vec.validate_dim(int(self.embedding.dim))
        if self._vec_dim is None:
            self.backend.create(dim)
            self._set_meta("embedding_dim", str(dim))
            self._set_meta("vec_backend", self.backend.name)
            if self.configured_model:
                self._set_meta("embedding_model", self.configured_model)
                self.index_model = self.configured_model
            self._vec_dim = dim
        elif self._vec_dim != dim:
            raise ReindexRequired(
                f"색인 차원 {self._vec_dim} ≠ 임베딩 차원 {dim}. DB 를 재색인하세요."
            )

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> SQLiteDocumentRepository:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── 쓰기 ─────────────────────────────────────────────────────
    async def upsert(self, docs: list[Document], chunks: list[Chunk]) -> None:
        if not docs and not chunks:
            return
        vectors = await self.embedding.embed([c.text for c in chunks]) if chunks else []
        if len(vectors) != len(chunks):
            raise ValueError("임베딩 개수가 청크 개수와 다릅니다")
        await asyncio.to_thread(self._upsert_sync, docs, chunks, vectors)

    def _upsert_sync(
        self, docs: list[Document], chunks: list[Chunk], vectors: list[list[float]]
    ) -> None:
        with self._lock:
            if chunks:
                self._ensure_vec_table()
            with self.conn:  # 단일 트랜잭션
                for doc in docs:
                    self.conn.execute(_INSERT_DOCUMENT, _mapping.document_to_row(doc))
                    self.conn.execute(_TOUCH_INGESTED, (doc.doc_id,))
                    self.conn.execute("DELETE FROM document_orgs WHERE doc_id = ?", (doc.doc_id,))
                    self.conn.executemany(
                        "INSERT INTO document_orgs(doc_id, org) VALUES (?, ?)",
                        [(doc.doc_id, org) for org in dict.fromkeys(doc.orgs)],
                    )
                self._replace_chunks(chunks, vectors)
        _secure_paths(self.db_path)

    def _replace_chunks(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        if not chunks:
            return
        touched = list(dict.fromkeys(c.doc_id for c in chunks))
        stale = [
            row["id"]
            for doc_id in touched
            for row in self.conn.execute("SELECT id FROM chunks WHERE doc_id = ?", (doc_id,))
        ]
        if stale:
            self.backend.delete(stale)
            self.conn.executemany("DELETE FROM chunks WHERE id = ?", [(i,) for i in stale])

        rowids: list[int] = []
        for chunk in chunks:
            cur = self.conn.execute(_INSERT_CHUNK, _mapping.chunk_to_row(chunk))
            rowids.append(int(cur.lastrowid))
        self.backend.add(list(zip(rowids, vectors, strict=True)))

    # ── 읽기 ─────────────────────────────────────────────────────
    async def count_by_source(self) -> dict[str, int]:
        return await asyncio.to_thread(self._count_by_source_sync)

    def _count_by_source_sync(self) -> dict[str, int]:
        with self._lock:
            rows = self.conn.execute("SELECT source, COUNT(*) FROM documents GROUP BY source")
            return {str(source): int(n) for source, n in rows}

    async def source_status(self) -> dict[str, dict[str, Any]]:
        return await asyncio.to_thread(self._source_status_sync)

    def _source_status_sync(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute(_SOURCE_STATUS).fetchall()
        return {
            str(source): {"count": int(n), "last_ingested": str(last)[:10] if last else None}
            for source, n, last in rows
        }

    async def find_identities(self, docs: list[Document]) -> dict[str, str]:
        """[4] IdentityLookupPort — {새 doc_id: 저장된 doc_id}. DOI·출원번호·보고서 과제번호·정규화
        제목으로 후보를 읽고 동일성 키(live_search.identity_keys)로 판정한다. 값은 전부 바인딩
        (E)."""
        if not docs:
            return {}
        return await asyncio.to_thread(self._find_identities_sync, docs[:MAX_IDENTITY_DOCS])

    def _find_identities_sync(self, docs: list[Document]) -> dict[str, str]:
        dois = sorted({v for d in docs if d.doi for v in (d.doi, d.doi.lower())})
        appnos = sorted({d.application_no for d in docs if d.application_no})
        project_nos = sorted(
            {
                str(d.raw["project_no"])
                for d in docs
                if d.doc_type in ("report", "internal_report") and d.raw.get("project_no")
            }
        )
        titles = sorted({t for d in docs if len(t := normalized_title(d.title)) >= 8})
        stored: dict[str, Document] = {}
        with self._lock:
            for sql, values in (
                (_BY_DOI, dois),
                (_BY_APPNO, appnos),
                (_BY_PROJECT_NO, project_nos),
                (_BY_NORM_TITLE, titles),
            ):
                if not values:
                    continue
                stmt = sql.replace("{marks}", _sql.placeholders(len(values)))
                for row in self.conn.execute(stmt, tuple(values)):
                    stored.setdefault(row["doc_id"], _mapping.row_to_document(row))
        return match_existing(docs, list(stored.values()))

    async def get_document(self, doc_id: str) -> Document | None:
        return await asyncio.to_thread(self._get_document_sync, doc_id)

    def _get_document_sync(self, doc_id: str) -> Document | None:
        with self._lock:
            row = self.conn.execute(_SELECT_DOCUMENT, (doc_id,)).fetchone()
        return _mapping.row_to_document(row) if row else None

    async def hybrid_search(
        self,
        queries: list[str],
        *,
        k: int = 20,
        orgs: list[str] | None = None,
        sources: list[str] | None = None,
    ) -> list[Chunk]:
        limit = _sql.clamp_k(k, max_k=self.max_k)
        cleaned = _sql.clamp_queries(
            queries, max_queries=self.max_queries, max_chars=self.max_query_chars
        )
        if not cleaned:
            return []
        vectors: list[list[float] | None]
        if self._vec_dim is None:  # 색인 전 — 벡터 랭킹 없음, 임베딩 계산도 하지 않는다
            vectors = [None] * len(cleaned)
        else:
            vectors = list(await self.embedding.embed_query(cleaned))
        return await asyncio.to_thread(
            self._hybrid_search_sync,
            cleaned,
            vectors,
            limit,
            _Filter(orgs=self._clean_names(orgs), sources=self._clean_names(sources)),
        )

    def _hybrid_search_sync(
        self,
        queries: list[str],
        vectors: list[list[float] | None],
        limit: int,
        flt: _Filter,
    ) -> list[Chunk]:
        fetch = limit * FETCH_MULTIPLIER
        with self._lock:
            rankings: list[list[str]] = []
            for query, vector in zip(queries, vectors, strict=True):
                rankings.append(self._fts_ids(query, fetch, flt))
                rankings.append(self._vec_ids(vector, fetch, flt))
            fused = reciprocal_rank_fusion(rankings, k=self.rrf_k)
            chunks = self._load_chunks([chunk_id for chunk_id, _ in fused[:limit]])
            return self._with_similarity(chunks, [v for v in vectors if v is not None])

    def _with_similarity(self, chunks: list[Chunk], vectors: list[list[float]]) -> list[Chunk]:
        """질의 벡터와의 코사인(여러 질의면 최댓값)을 Chunk.similarity 에. 색인이 없으면 None."""
        if not chunks or not vectors or self._vec_dim is None:
            return chunks
        marks = _sql.placeholders(len(chunks))
        rows = self.conn.execute(
            f"SELECT id, chunk_id FROM chunks WHERE chunk_id IN ({marks})",  # noqa: S608  # nosec B608
            tuple(c.chunk_id for c in chunks),
        ).fetchall()
        rowid_of = {row["chunk_id"]: row["id"] for row in rows}
        stored = self.backend.vectors(list(rowid_of.values()))
        queries = [_vec.normalize(v) for v in vectors]
        out: list[Chunk] = []
        for c in chunks:
            vec = stored.get(rowid_of.get(c.chunk_id, -1))
            if vec is None:
                out.append(c)
                continue
            score = max(_vec.cosine(q, vec) for q in queries)
            out.append(c.model_copy(update={"similarity": round(score, 6)}))
        return out

    async def find_similar(
        self, text: str, *, k: int = 10, sources: list[str] | None = None
    ) -> list[tuple[Document, float]]:
        limit = _sql.clamp_k(k, max_k=self.max_k)
        query = _sql.clamp_query(text, max_chars=self.max_query_chars)
        if not query or self._vec_dim is None:
            return []
        vector = await self._query_vector(query)
        return await asyncio.to_thread(
            self._find_similar_sync, vector, limit, self._clean_names(sources)
        )

    async def _query_vector(self, query: str) -> list[float]:
        """같은 질의 글의 임베딩은 한 번만 — precheck 가 자료원별로 여러 번 찾는다(ADR 0028)."""
        memo = self._query_memo
        if memo is not None and memo[0] == query:
            return memo[1]
        vector = (await self.embedding.embed_query([query]))[0]
        self._query_memo = (query, vector)
        return vector

    def _find_similar_sync(
        self, vector: list[float], limit: int, sources: list[str] | None = None
    ) -> list[tuple[Document, float]]:
        """자료원 필터가 있으면 그 자료원의 청크 안에서만 KNN(사전 필터) — 과제형 자료원(own·alio·
        ntis 과제·g2b)은 전체 색인의 일부라 상위 k×4 를 거르는 방식으로는 모자란다(ADR 0028)."""
        allowed = set(sources or [])
        fetch = limit * FETCH_MULTIPLIER
        with self._lock:
            if allowed:
                marks = _sql.placeholders(len(allowed))
                hits = self.backend.search_within(
                    vector,
                    fetch,
                    _ROWIDS_OF_SOURCES.replace("{sources}", marks),
                    tuple(sorted(allowed)),
                )
            else:
                hits = self.backend.search(vector, fetch)
            return self._rank_documents(hits, limit, allowed)

    def _rank_documents(
        self, hits: list[tuple[int, float]], limit: int, allowed: set[str]
    ) -> list[tuple[Document, float]]:
        best: dict[str, float] = {}
        for rowid, score in hits:
            if score <= self.min_similarity:
                continue
            row = self.conn.execute("SELECT doc_id FROM chunks WHERE id = ?", (rowid,)).fetchone()
            if row is None:
                continue
            doc_id = row["doc_id"]
            if score > best.get(doc_id, -1.0):
                best[doc_id] = score
        ranked = sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))
        today = self.today()
        out: list[tuple[Document, float]] = []
        for doc_id, score in ranked:
            doc = self._get_document_sync(doc_id)
            if doc is None or not doc.is_valid_on(today):  # 만료 문서는 precheck 에서 제외
                continue
            if allowed and doc.source not in allowed:
                continue
            out.append((doc, score))
            if len(out) >= limit:
                break
        return out

    # ── 내부 검색 ────────────────────────────────────────────────
    def _clean_names(self, names: list[str] | None) -> list[str]:
        if not names:
            return []
        return list(dict.fromkeys(n for n in names if isinstance(n, str) and n))[: self.max_k]

    def _fts_ids(self, query: str, fetch: int, flt: _Filter) -> list[str]:
        match = _sql.quote_fts_query(query, max_chars=self.max_query_chars)
        if not match:
            return []
        today = self.today().isoformat()
        if flt:
            sql = _FTS_SEARCH_FILTERED.replace("{filters}", flt.sql())
            params: tuple[object, ...] = (match, today, *flt.params(), fetch)
        else:
            sql, params = _FTS_SEARCH, (match, today, fetch)
        # quote_fts_query 가 문법적으로 안전한 식만 만들므로 예외를 삼키지 않는다.
        return [row["chunk_id"] for row in self.conn.execute(sql, params)]

    def _vec_ids(self, vector: list[float] | None, fetch: int, flt: _Filter) -> list[str]:
        if vector is None or self._vec_dim is None:
            return []
        want = fetch * (FETCH_MULTIPLIER if flt else 1)
        while True:
            hits = [
                (rowid, score)
                for rowid, score in self.backend.search(vector, want)
                if score > self.min_similarity
            ]
            if not hits:
                return []
            allowed = self._chunk_ids_for([rowid for rowid, _ in hits], flt)
            out = [allowed[rowid] for rowid, _ in hits if rowid in allowed]
            # 필터로 모자라고 색인에 더 남아 있으면 더 넓게 다시 받는다 (상한까지).
            if len(out) >= fetch or not flt or len(hits) < want or want >= VEC_FETCH_CAP:
                return out[:fetch]
            want = min(want * FETCH_MULTIPLIER, VEC_FETCH_CAP)

    def _chunk_ids_for(self, rowids: list[int], flt: _Filter) -> dict[int, str]:
        """벡터 히트 rowid → chunk_id. 만료 문서·org/source 필터 밖 청크는 빠진다."""
        out: dict[int, str] = {}
        today = self.today().isoformat()
        for start in range(0, len(rowids), self.max_k):
            batch = rowids[start : start + self.max_k]
            marks = _sql.placeholders(len(batch))
            # marks·placeholders 는 정수 개수만 받는다 (_sql.placeholders).
            sql = (
                f"SELECT c.id, c.chunk_id FROM chunks c JOIN documents d ON d.doc_id = c.doc_id "  # noqa: S608  # nosec B608
                f"WHERE c.id IN ({marks}) AND {_VALID}{flt.sql()}"
            )
            params: tuple[object, ...] = (*batch, today, *flt.params())
            for row in self.conn.execute(sql, params):
                out[row["id"]] = row["chunk_id"]
        return out

    # ── 유지보수 (DatabaseMaintenancePort) ─────────────────────
    async def reindex(self) -> dict[str, int | str | None]:
        """모든 청크를 현재 임베딩 모델로 다시 임베딩한다 (차원·모델이 바뀌어도 된다).

        벡터 표를 비우고 메타(embedding_dim·embedding_model)를 지운 뒤 배치로 다시 채운다.
        FTS·문서·청크 행은 그대로.
        """
        rows = await asyncio.to_thread(self._all_chunks_sync)
        dim = _vec.validate_dim(int(self.embedding.dim))
        vectors: list[tuple[int, list[float]]] = []
        for start in range(0, len(rows), REINDEX_BATCH):
            batch = rows[start : start + REINDEX_BATCH]
            embedded = await self.embedding.embed([text for _, text in batch])
            if len(embedded) != len(batch):
                raise ValueError("임베딩 개수가 청크 개수와 다릅니다")
            vectors.extend(zip((rowid for rowid, _ in batch), embedded, strict=True))
        await asyncio.to_thread(self._rebuild_vectors_sync, dim, vectors)
        return {"chunks": len(rows), "dim": dim, "model": self.index_model}

    def _all_chunks_sync(self) -> list[tuple[int, str]]:
        with self._lock:
            return [(int(r["id"]), str(r["text"])) for r in self.conn.execute(_SELECT_ALL_CHUNKS)]

    def _rebuild_vectors_sync(self, dim: int, vectors: list[tuple[int, list[float]]]) -> None:
        with self._lock, self.conn:
            for table in ("chunk_embeddings", "chunk_vec"):
                self.conn.execute(f"DROP TABLE IF EXISTS {table}")  # noqa: S608  # nosec B608 - 상수
            self.conn.execute("DELETE FROM meta WHERE key IN ('embedding_dim', 'embedding_model')")
            self._vec_dim = None
            self._query_memo = None
            self.index_model = None
            self.backend.create(dim)
            self._set_meta("embedding_dim", str(dim))
            self._set_meta("vec_backend", self.backend.name)
            if self.configured_model:
                self._set_meta("embedding_model", self.configured_model)
                self.index_model = self.configured_model
            self._vec_dim = dim
            if vectors:
                self.backend.add(vectors)
        _secure_paths(self.db_path)

    async def backup(self, out: str | Path) -> Path:
        """VACUUM INTO 로 일관된 사본을 만든다. 기존 파일은 덮어쓰지 않는다 (SQLite 가 거부)."""
        return await asyncio.to_thread(self._backup_sync, Path(out))

    def _backup_sync(self, out: Path) -> Path:
        out.parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            os.chmod(out.parent, DB_DIR_MODE)
        with self._lock:
            self.conn.execute("VACUUM INTO ?", (str(out),))
        if os.name != "nt":
            os.chmod(out, DB_FILE_MODE)
        return out

    # ── 표 사실 (TableFactRepository, P2-8) ───────────────
    async def replace_facts(self, doc_id: str, facts: list[TableFact]) -> int:
        return await asyncio.to_thread(self._replace_facts_sync, doc_id, facts)

    def _replace_facts_sync(self, doc_id: str, facts: list[TableFact]) -> int:
        with self._lock, self.conn:
            self.conn.execute(_DELETE_FACTS, (doc_id,))
            self.conn.executemany(_INSERT_FACT, [_fact_row(doc_id, f) for f in facts])
        return len(facts)

    async def search_facts(self, query: str, *, k: int = 20) -> list[TableFact]:
        limit = _sql.clamp_k(k, max_k=self.max_k)
        tokens = _sql.fts_tokens(query, max_chars=self.max_query_chars, max_tokens=MAX_FACT_TOKENS)
        if not tokens:
            return []
        return await asyncio.to_thread(self._search_facts_sync, tokens, limit)

    def _search_facts_sync(self, tokens: list[str], limit: int) -> list[TableFact]:
        # 조건 개수만 정수로 조립하고 패턴은 전부 바인딩한다 (보안 E)
        where = " AND ".join(["item LIKE ? ESCAPE '\\'"] * len(tokens))
        sql = f"{_SELECT_FACTS} WHERE {where} ORDER BY id LIMIT ?"  # noqa: S608  # nosec B608
        params = (*[_like_pattern(t) for t in tokens], limit)
        with self._lock:
            return [_row_to_fact(r) for r in self.conn.execute(sql, params)]

    async def facts_for(self, doc_ids: list[str]) -> dict[str, list[TableFact]]:
        ids = self._clean_names(doc_ids)
        if not ids:
            return {}
        return await asyncio.to_thread(self._facts_for_sync, ids)

    def _facts_for_sync(self, doc_ids: list[str]) -> dict[str, list[TableFact]]:
        out: dict[str, list[TableFact]] = {}
        with self._lock:
            for start in range(0, len(doc_ids), self.max_k):
                batch = doc_ids[start : start + self.max_k]
                sql = (
                    f"{_SELECT_FACTS} WHERE doc_id IN ({_sql.placeholders(len(batch))}) "  # noqa: S608  # nosec B608
                    "ORDER BY id"
                )
                for row in self.conn.execute(sql, tuple(batch)):
                    out.setdefault(row["doc_id"], []).append(_row_to_fact(row))
        return out

    async def fact_counts(self) -> dict[str, int]:
        return await asyncio.to_thread(self._fact_counts_sync)

    def _fact_counts_sync(self) -> dict[str, int]:
        with self._lock:
            return {str(src): int(n) for src, n in self.conn.execute(_FACT_COUNTS)}

    # ── 코퍼스 접근 (CorpusAccessPort, P2-9) ─────────────
    async def sample_chunks(self, limit: int) -> list[Chunk]:
        return await asyncio.to_thread(self._sample_chunks_sync, max(0, int(limit)))

    def _sample_chunks_sync(self, limit: int) -> list[Chunk]:
        """자료원마다 limit/자료원수 개씩 (id 순 — 결정적). 한 자료원이 표본을 독차지하지 않도록."""
        with self._lock:
            sources = [str(r[0]) for r in self.conn.execute(_SAMPLE_SOURCES)]
            if not sources or limit == 0:
                return []
            per_source = max(1, limit // len(sources))
            out: list[Chunk] = []
            for source in sources:
                rows = self.conn.execute(_SAMPLE_CHUNKS, (source, per_source)).fetchall()
                out.extend(_mapping.row_to_chunk(r) for r in rows)
            return out[:limit]

    async def documents_of(self, source: str, *, limit: int | None = None) -> list[Document]:
        cap = _sql.MAX_K * 100 if limit is None else max(0, int(limit))
        return await asyncio.to_thread(self._documents_of_sync, str(source), cap)

    def _documents_of_sync(self, source: str, limit: int) -> list[Document]:
        with self._lock:
            rows = self.conn.execute(_DOCUMENTS_OF, (source, limit)).fetchall()
        return [_mapping.row_to_document(r) for r in rows]

    def _load_chunks(self, chunk_ids: list[str]) -> list[Chunk]:
        if not chunk_ids:
            return []
        found: dict[str, Chunk] = {}
        for start in range(0, len(chunk_ids), self.max_k):
            batch = chunk_ids[start : start + self.max_k]
            sql = (
                "SELECT c.chunk_id, c.doc_id, c.ordinal, c.heading, c.text, "  # noqa: S608  # nosec B608
                "d.text_basis AS basis, d.visibility AS visibility "
                "FROM chunks c JOIN documents d ON d.doc_id = c.doc_id "
                f"WHERE c.chunk_id IN ({_sql.placeholders(len(batch))})"
            )
            for row in self.conn.execute(sql, tuple(batch)):
                found[row["chunk_id"]] = _mapping.row_to_chunk(row)
        return [found[cid] for cid in chunk_ids if cid in found]


def _fact_row(doc_id: str, f: TableFact) -> tuple[object, ...]:
    return (
        doc_id,
        f.item,
        f.year,
        f.unit,
        float(f.value),
        f.value_text,
        f.page,
        f.sheet,
        f.row_label,
        f.col_label,
        f.basis,
    )


def _row_to_fact(row: sqlite3.Row) -> TableFact:
    return TableFact(
        doc_id=row["doc_id"],
        item=row["item"],
        year=row["year"],
        unit=row["unit"],
        value=Decimal(repr(float(row["value"]))),
        value_text=row["value_text"],
        page=row["page"],
        sheet=row["sheet"],
        row_label=row["row_label"],
        col_label=row["col_label"],
        basis=row["basis"],
    )


def _like_pattern(token: str) -> str:
    """LIKE 토큰 — 와일드카드·이스케이프 문자를 리터럴로."""
    escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
