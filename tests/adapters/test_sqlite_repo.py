import os
import sqlite3
from datetime import date

import pytest

from rra.adapters.persistence import ReindexRequired, SQLiteDocumentRepository, _vec
from rra.adapters.persistence.migrations import runner
from rra.domain.models import Chunk, Document
from tests.fakes import DeterministicEmbedding

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture(params=["bruteforce", "sqlite-vec"])
def backend_name(request):
    if request.param == "sqlite-vec":
        pytest.importorskip("sqlite_vec")
    return request.param


@pytest.fixture
def repo(tmp_path, backend_name):
    r = SQLiteDocumentRepository(
        tmp_path / "data" / "rra.sqlite",
        DeterministicEmbedding(),
        prefer_extension=backend_name == "sqlite-vec",
    )
    if r.backend.name != backend_name:  # pragma: no cover - 환경 방어
        pytest.skip(f"{backend_name} 백엔드를 사용할 수 없음")
    yield r
    r.close()


def make_docs():
    return [
        Document(
            doc_id="alio:1",
            source="alio",
            doc_type="internal_report",
            title="궤도 상태 자동 감지 연구",
            body="궤도의 틀림을 자동으로 감지한다",
            pub_date=date(2023, 5, 1),
            orgs=["korail", "krri"],
            authors=["홍길동"],
            codes=["B61K"],
            department="철도연구원",
            project_period=(date(2022, 1, 1), date(2023, 12, 31)),
            toc=["1장 서론", "2장 방법"],
            raw={"src": "x"},
            doi=None,
        ),
        Document(
            doc_id="openalex:W1",
            source="openalex",
            doc_type="paper",
            title="Track geometry monitoring",
            abstract="IMU based track geometry monitoring",
            orgs=["external"],
            doi="10.1/x",
        ),
    ]


def make_chunks():
    return [
        Chunk(
            chunk_id="alio:1#0",
            doc_id="alio:1",
            ordinal=0,
            heading="1장 서론",
            text="궤도의 틀림을 자동으로 감지한다",
        ),
        Chunk(
            chunk_id="openalex:W1#0",
            doc_id="openalex:W1",
            ordinal=0,
            text="IMU based track geometry monitoring",
        ),
    ]


@pytest.fixture
async def loaded(repo):
    await repo.upsert(make_docs(), make_chunks())
    return repo


# ── 스키마·마이그레이션 ──────────────────────────────────────────
def test_migration_is_applied_and_idempotent(repo):
    assert runner.current_version(repo.conn) == 5 and repo.schema_version == 5
    assert runner.migrate(repo.conn) == 5
    assert [v for v, _ in runner.applied_versions(repo.conn)] == [1, 2, 3, 4, 5]  # 적용 이력 표


async def test_reopening_reuses_the_pinned_backend(tmp_path, loaded):
    path = loaded.db_path
    loaded.close()
    again = SQLiteDocumentRepository(path, DeterministicEmbedding())
    assert again.backend.name == loaded.backend.name
    assert await again.get_document("alio:1") is not None
    again.close()


# ── 쓰기 ─────────────────────────────────────────────────────────
async def test_upsert_is_idempotent(repo):
    for _ in range(3):
        await repo.upsert(make_docs(), make_chunks())
    counts = {
        table: repo.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]  # noqa: S608
        for table in ("documents", "chunks", "chunks_fts", "document_orgs")
    }
    assert counts == {"documents": 2, "chunks": 2, "chunks_fts": 2, "document_orgs": 3}
    assert len(await repo.hybrid_search(["궤도"], k=10)) == 1


async def test_upsert_replaces_only_touched_documents_chunks(loaded):
    await loaded.upsert(
        [],
        [Chunk(chunk_id="alio:1#0", doc_id="alio:1", ordinal=0, text="완전히 다른 본문")],
    )
    assert loaded.conn.execute("SELECT count(*) FROM chunks").fetchone()[0] == 2
    hit = await loaded.hybrid_search(["다른 본문"], k=5)
    assert hit[0].text == "완전히 다른 본문"


async def test_chunk_without_document_violates_foreign_key(repo):
    with pytest.raises(sqlite3.IntegrityError):
        await repo.upsert([], [Chunk(chunk_id="ghost#0", doc_id="ghost", ordinal=0, text="x")])


async def test_embedding_dimension_change_requires_reindex(loaded):
    loaded.embedding = DeterministicEmbedding(dim=8)
    with pytest.raises(ReindexRequired):
        await loaded.upsert(make_docs(), make_chunks())


# ── 읽기 ─────────────────────────────────────────────────────────
async def test_get_document_round_trips_every_field(loaded):
    doc = await loaded.get_document("alio:1")
    original = make_docs()[0]
    assert doc == original
    assert doc.project_period == (date(2022, 1, 1), date(2023, 12, 31))
    assert doc.toc == ["1장 서론", "2장 방법"]
    assert await loaded.get_document("nope") is None


async def test_fts_prefix_matches_korean_particles(loaded):
    assert [c.chunk_id for c in await loaded.hybrid_search(["궤도"], k=5)] == ["alio:1#0"]


async def test_hybrid_search_ranks_document_matching_both_signals_first(loaded):
    hits = await loaded.hybrid_search(["track geometry monitoring"], k=5)
    assert hits[0].chunk_id == "openalex:W1#0"


async def test_orgs_filter(loaded):
    assert [
        c.chunk_id for c in await loaded.hybrid_search(["궤도 track"], k=5, orgs=["korail"])
    ] == ["alio:1#0"]
    assert [
        c.chunk_id for c in await loaded.hybrid_search(["궤도 track"], k=5, orgs=["external"])
    ] == ["openalex:W1#0"]
    assert await loaded.hybrid_search(["궤도 track"], k=5, orgs=["없는기관"]) == []


async def test_sources_filter(loaded):
    assert [
        c.doc_id for c in await loaded.hybrid_search(["궤도 track"], k=5, sources=["openalex"])
    ] == ["openalex:W1"]
    assert [
        c.doc_id for c in await loaded.hybrid_search(["궤도 track"], k=5, sources=["alio"])
    ] == ["alio:1"]
    assert await loaded.hybrid_search(["궤도 track"], k=5, sources=["없는자료원"]) == []
    # orgs 와 함께 — 둘 다 만족해야 한다
    both = await loaded.hybrid_search(["궤도 track"], k=5, orgs=["korail"], sources=["openalex"])
    assert both == []
    assert [
        c.doc_id
        for c in await loaded.hybrid_search(["궤도 track"], k=5, orgs=["korail"], sources=["alio"])
    ] == ["alio:1"]


async def test_vector_fetch_widens_until_the_filtered_source_is_found(repo):
    """상위 벡터 목록을 다른 자료원이 메워도 필터 자료원을 찾을 때까지 더 받는다 (상한까지)."""
    from rra.adapters.persistence import sqlite_repo as mod

    own = [
        Document(doc_id=f"own:{i}", source="own", doc_type="rnd_project", title=f"궤도 {i}")
        for i in range(40)
    ]
    paper = Document(
        doc_id="openalex:W9", source="openalex", doc_type="paper", title="rail paper", doi="10.1/z"
    )
    chunks = [
        Chunk(chunk_id=f"own:{i}#0", doc_id=f"own:{i}", ordinal=0, text=f"궤도 틀림 감지 {i}")
        for i in range(40)
    ] + [Chunk(chunk_id="openalex:W9#0", doc_id="openalex:W9", ordinal=0, text="zebra unrelated")]
    await repo.upsert(own + [paper], chunks)
    calls: list[int] = []
    inner = repo.backend.search

    def spy(vector, k):
        calls.append(k)
        return inner(vector, k)

    repo.backend.search = spy
    repo.min_similarity = -1.0  # 무관한 논문(코사인 ≈ 0)도 벡터 목록에 남겨 순위 41 로 둔다
    hits = await repo.hybrid_search(["궤도 틀림 감지"], k=1, sources=["openalex"])
    assert [c.doc_id for c in hits] == ["openalex:W9"]
    # 벡터: 1×4(fetch)×4(필터) = 16 → 모자라 64 로 다시. FTS 는 자료원 필터로 바로 찾는다.
    assert calls == [16, 64]
    assert mod.VEC_FETCH_CAP == 4096


async def test_k_and_query_count_are_clamped(loaded):
    assert len(await loaded.hybrid_search(["궤도 track"], k=10**9)) == 2
    assert await loaded.hybrid_search([], k=5) == []
    assert await loaded.hybrid_search(["   ", ""], k=5) == []
    assert len(await loaded.hybrid_search(["궤도"] * 50, k=5)) == 1


async def test_search_on_empty_database_returns_nothing(repo):
    assert await repo.hybrid_search(["궤도"], k=5) == []
    assert await repo.find_similar("궤도") == []


async def test_find_similar_scores_documents_by_best_chunk(loaded):
    hits = await loaded.find_similar("궤도의 틀림을 자동으로 감지한다", k=5)
    assert hits[0][0].doc_id == "alio:1"
    assert hits[0][1] == pytest.approx(1.0)
    assert all(0.0 <= score <= 1.0 for _, score in hits)
    assert [s for _, s in hits] == sorted((s for _, s in hits), reverse=True)


async def test_search_input_is_never_interpreted_as_sql(loaded):
    await loaded.hybrid_search(["'; DROP TABLE chunks; --", '" OR 1=1 --'], k=5)
    assert loaded.conn.execute("SELECT count(*) FROM chunks").fetchone()[0] == 2


# ── 보안 E: 파일 권한 ────────────────────────────────────────────
@pytest.mark.skipif(os.name == "nt", reason="POSIX 권한 비트 없음")
def test_database_files_are_owner_only(loaded):
    assert os.stat(loaded.db_path).st_mode & 0o777 == 0o600
    assert os.stat(loaded.db_path.parent).st_mode & 0o777 == 0o700


@pytest.mark.skipif(os.name == "nt", reason="POSIX 권한 비트 없음")
def test_loose_permissions_are_tightened_on_open(tmp_path):
    path = tmp_path / "data" / "rra.sqlite"
    path.parent.mkdir(parents=True)
    path.touch(mode=0o666)
    os.chmod(path.parent, 0o755)  # noqa: S103 - 느슨한 권한을 일부러 만들어 놓고 검증
    repo = SQLiteDocumentRepository(path, DeterministicEmbedding())
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert os.stat(path.parent).st_mode & 0o777 == 0o700
    repo.close()


# ── 벡터 백엔드 단위 ─────────────────────────────────────────────
def test_zero_vector_has_zero_similarity():
    assert _vec.cosine(_vec.normalize([0.0, 0.0]), [1.0, 0.0]) == 0.0


def test_pack_round_trip():
    assert _vec.unpack(_vec.pack([0.5, -0.25])) == [0.5, -0.25]


@pytest.mark.parametrize("bad", ["768", 0, -1, 10**6, True])
def test_validate_dim_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        _vec.validate_dim(bad)


async def test_text_basis_roundtrip_and_chunk_basis(tmp_path):
    from rra.domain.models import Chunk, Document

    repo = SQLiteDocumentRepository(tmp_path / "b.db", DeterministicEmbedding())
    doc = Document(
        doc_id="alio:s1",
        source="alio",
        doc_type="internal_report",
        title="궤도 요약",
        body="■ 연구목적 궤도 상태 진단",
        text_basis="summary",
    )
    await repo.upsert(
        [doc], [Chunk(chunk_id="alio:s1#0", doc_id="alio:s1", ordinal=0, text=doc.body)]
    )
    assert (await repo.get_document("alio:s1")).text_basis == "summary"
    (chunk,) = await repo.hybrid_search(["궤도"], k=5)
    assert chunk.basis == "summary"


def test_migration_002_backfills_existing_rows(tmp_path):
    import sqlite3

    conn = sqlite3.connect(tmp_path / "old.db")
    first = [(v, p) for v, p in runner.discover() if v == 1]
    conn.executescript(first[0][1].read_text(encoding="utf-8"))
    conn.execute("PRAGMA user_version = 1")
    conn.executemany(
        "INSERT INTO documents (doc_id, source, doc_type, title) VALUES (?,?,?,?)",
        [("alio:1", "alio", "internal_report", "a"), ("ntis:1", "ntis", "rnd_project", "b")],
    )
    conn.commit()
    assert runner.migrate(conn) == 5  # 002 백필 뒤 003·004·005 까지 적용
    rows = dict(conn.execute("SELECT doc_id, text_basis FROM documents"))
    assert rows == {"alio:1": "full_text", "ntis:1": "abstract"}


async def test_count_by_source(tmp_path):
    from rra.adapters.persistence import SQLiteDocumentRepository
    from tests.fakes import FakeEmbedding

    repo = SQLiteDocumentRepository(tmp_path / "c.sqlite", FakeEmbedding())
    assert await repo.count_by_source() == {}
    await repo.upsert(make_docs(), [])
    counts = await repo.count_by_source()
    assert sum(counts.values()) == len(make_docs())
    assert set(counts) == {d.source for d in make_docs()}


# ── [2] DB 정비 (2026-10-26) ─────────────────────────────────────
def _old_schema_db(path, docs):
    """001·002 만 적용된 구버전 DB 를 만든다 (valid_until·visibility·schema_version 없음)."""
    import shutil

    old_dir = path.parent / "old_migrations"
    old_dir.mkdir(parents=True)
    for sql in sorted(runner.MIGRATIONS_DIR.glob("00[12]_*.sql")):
        shutil.copy(sql, old_dir / sql.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    assert runner.migrate(conn, old_dir) == 2
    cols = [r[1] for r in conn.execute("PRAGMA table_info(documents)")]
    assert "valid_until" not in cols and "visibility" not in cols
    for d in docs:  # 구버전 열만으로 적재
        conn.execute(
            "INSERT INTO documents(doc_id, source, doc_type, title, body, text_basis) "
            "VALUES (?,?,?,?,?,?)",
            (d.doc_id, d.source, d.doc_type, d.title, d.body, "full_text"),
        )
        conn.execute(
            "INSERT INTO chunks(chunk_id, doc_id, ordinal, text) VALUES (?,?,?,?)",
            (f"{d.doc_id}#0", d.doc_id, 0, d.body or d.title),
        )
    conn.commit()
    conn.close()


async def test_old_schema_is_migrated_and_still_searchable(tmp_path):
    path = tmp_path / "data" / "rra.sqlite"
    _old_schema_db(path, make_docs())
    repo = SQLiteDocumentRepository(path, DeterministicEmbedding(), prefer_extension=False)
    assert repo.schema_version == 5
    assert [v for v, _ in runner.applied_versions(repo.conn)] == [1, 2, 3, 4, 5]
    doc = await repo.get_document("alio:1")
    assert doc.visibility == "public" and doc.valid_until is None  # 기본값
    hits = await repo.hybrid_search(["궤도 틀림"], k=5)  # 벡터 색인 전 — FTS 만으로 검색
    assert [c.doc_id for c in hits] == ["alio:1"]
    await repo.upsert(make_docs(), make_chunks())  # 새 열로 다시 적재해도 된다
    assert len(await repo.hybrid_search(["궤도"], k=5)) == 1
    repo.close()


async def test_expired_documents_are_excluded_from_search_and_precheck(tmp_path):
    today = {"d": date(2026, 10, 26)}
    repo = SQLiteDocumentRepository(
        tmp_path / "rra.sqlite",
        DeterministicEmbedding(),
        prefer_extension=False,
        today=lambda: today["d"],
    )
    docs = make_docs()
    docs[0] = docs[0].model_copy(
        update={"valid_until": date(2026, 10, 31), "visibility": "internal"}
    )
    await repo.upsert(docs, make_chunks())
    stored = await repo.get_document("alio:1")
    assert stored.valid_until == date(2026, 10, 31) and stored.visibility == "internal"
    text = "궤도의 틀림을 자동으로 감지한다"  # 청크 본문과 같은 토큰 → FTS·벡터 모두 맞는다
    assert [c.doc_id for c in await repo.hybrid_search([text], k=5)] == ["alio:1"]
    assert [d.doc_id for d, _ in await repo.find_similar(text, k=5)] == ["alio:1"]

    today["d"] = date(2026, 11, 1)  # 만료 다음 날
    assert await repo.hybrid_search([text], k=5) == []  # FTS·벡터 모두 제외
    assert await repo.find_similar(text, k=5) == []  # precheck 도 제외
    assert await repo.get_document("alio:1") is not None  # 문서 자체는 남아 있다
    repo.close()


async def test_embedding_model_is_recorded_and_mismatch_warns(tmp_path, caplog):
    path = tmp_path / "rra.sqlite"
    repo = SQLiteDocumentRepository(path, DeterministicEmbedding(), prefer_extension=False)
    assert repo.index_model is None  # 색인 전
    await repo.upsert(make_docs(), make_chunks())
    assert repo.index_model == "fake/deterministic-v1" and not repo.index_model_mismatch
    repo.close()

    with caplog.at_level("WARNING", logger="rra.persistence"):
        again = SQLiteDocumentRepository(
            path, DeterministicEmbedding(model_name="fake/v2"), prefer_extension=False
        )
    assert again.index_model_mismatch and "db.embedding_model_mismatch" in caplog.text
    assert "fake/v2" in caplog.text and "rra reindex" in caplog.text
    again.close()


async def test_reindex_rebuilds_vectors_for_new_model_and_dimension(tmp_path):
    path = tmp_path / "rra.sqlite"
    repo = SQLiteDocumentRepository(path, DeterministicEmbedding(), prefer_extension=False)
    await repo.upsert(make_docs(), make_chunks())
    repo.close()
    again = SQLiteDocumentRepository(
        path, DeterministicEmbedding(dim=8, model_name="fake/v2"), prefer_extension=False
    )
    assert again.index_model_mismatch
    with pytest.raises(ReindexRequired):
        await again.upsert(make_docs(), make_chunks())
    stats = await again.reindex()
    assert stats == {"chunks": 2, "dim": 8, "model": "fake/v2"}
    assert not again.index_model_mismatch and again._vec_dim == 8
    assert again.conn.execute("SELECT count(*) FROM chunk_embeddings").fetchone()[0] == 2
    hits = await again.hybrid_search(["track geometry"], k=5)
    assert hits and hits[0].doc_id == "openalex:W1"
    await again.upsert(make_docs(), make_chunks())  # 새 차원으로 적재 가능
    again.close()


async def test_backup_is_a_consistent_copy_with_owner_only_mode(tmp_path, loaded):
    out = tmp_path / "backups" / "rra-20261026-033000.sqlite"
    path = await loaded.backup(out)
    assert path == out and out.is_file()
    if os.name != "nt":
        assert os.stat(out).st_mode & 0o777 == 0o600
    copy = sqlite3.connect(out)
    assert copy.execute("SELECT count(*) FROM documents").fetchone()[0] == 2
    assert copy.execute("PRAGMA user_version").fetchone()[0] == 5
    copy.close()
    with pytest.raises(sqlite3.OperationalError):  # 덮어쓰지 않는다
        await loaded.backup(out)


async def test_source_status_counts_and_last_ingested_date(loaded):
    status = await loaded.source_status()
    assert set(status) == {"alio", "openalex"}
    assert status["alio"]["count"] == 1 and len(status["alio"]["last_ingested"]) == 10  # YYYY-MM-DD
    assert status["alio"]["last_ingested"][:2] == "20"


# ── 검색 결과의 질의 코사인 (Chunk.similarity) ─────────────────────────────
async def test_hybrid_search_fills_query_similarity_on_both_backends(loaded):
    hits = await loaded.hybrid_search(["궤도의 틀림을 자동으로 감지한다"], k=5)
    assert hits and all(c.similarity is not None and 0.0 <= c.similarity <= 1.0 for c in hits)
    assert {c.chunk_id: c.similarity for c in hits}["alio:1#0"] > 0.99  # 본문과 같은 글
    multi = await loaded.hybrid_search(
        ["궤도의 틀림을 자동으로 감지한다", "IMU based track geometry monitoring"], k=5
    )
    by_id = {c.chunk_id: c.similarity for c in multi}
    assert by_id["alio:1#0"] > 0.99 and by_id["openalex:W1#0"] > 0.99  # 질의별 최댓값
    assert all(c.similarity is not None for c in multi)


async def test_similarity_is_none_before_any_vector_index(repo):
    assert await repo.hybrid_search(["궤도"], k=5) == []  # 색인 전: 빈 결과이지 오류가 아니다


async def test_backend_vectors_returns_stored_normalized_vectors(loaded):
    rowids = [row[0] for row in loaded.conn.execute("SELECT id FROM chunks ORDER BY id")]
    got = loaded.backend.vectors([*rowids, 999_999])
    assert set(got) == set(rowids)
    for vec in got.values():
        assert len(vec) == loaded._vec_dim
        assert abs(sum(v * v for v in vec) - 1.0) < 1e-4  # 정규화 저장
