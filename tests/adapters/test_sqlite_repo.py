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
    assert runner.current_version(repo.conn) == 2
    assert runner.migrate(repo.conn) == 2


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
    assert runner.migrate(conn) == 2
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
