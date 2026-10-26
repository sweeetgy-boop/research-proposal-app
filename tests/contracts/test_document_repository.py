"""DocumentRepository 계약 테스트 — 어댑터 무관. SQLite(bruteforce·sqlite-vec)와 InMemory fake 가
같은 테스트를 통과해야 한다. 어댑터별 세부(SQL·파일 권한·백엔드 고정)는 tests/adapters 에.

계약:
- 포트 isinstance, upsert 멱등, get_document 왕복(visibility·valid_until 포함)·없으면 None
- count_by_source 는 있는 자료원만
- hybrid_search: 빈 질의 → [], 결과는 Chunk ≤ k, 적재된 문서의 청크만, 만료(valid_until 경과) 제외
- find_similar: (Document, 0~1 점수) 내림차순 ≤ k, 본문과 같은 글이면 그 문서가 1위, 만료 제외
"""

from __future__ import annotations

from datetime import date

import pytest

from rra.application.ports import DocumentRepository
from rra.domain.models import Chunk, Document
from tests.fakes import DeterministicEmbedding, InMemoryRepository

TODAY = date(2026, 10, 26)


def docs():
    return [
        Document(
            doc_id="alio:1",
            source="alio",
            doc_type="internal_report",
            title="궤도 상태 자동 감지 연구",
            body="궤도의 틀림을 자동으로 감지한다",
            orgs=["korail"],
            department="철도연구원",
            text_basis="summary",
            visibility="internal",
            valid_until=date(2026, 12, 31),
        ),
        Document(
            doc_id="openalex:W1",
            source="openalex",
            doc_type="paper",
            title="Track geometry monitoring",
            abstract="IMU based track geometry monitoring",
            orgs=["external"],
            text_basis="abstract",
        ),
        Document(
            doc_id="ntis:old",
            source="ntis",
            doc_type="rnd_project",
            title="만료된 과제 공고",
            abstract="만료된 과제 공고 본문",
            text_basis="abstract",
            valid_until=date(2026, 1, 31),  # 이미 지났다
        ),
    ]


def chunks():
    return [
        Chunk(
            chunk_id="alio:1#0", doc_id="alio:1", ordinal=0, text="궤도의 틀림을 자동으로 감지한다"
        ),
        Chunk(
            chunk_id="openalex:W1#0",
            doc_id="openalex:W1",
            ordinal=0,
            text="IMU based track geometry",
        ),
        Chunk(chunk_id="ntis:old#0", doc_id="ntis:old", ordinal=0, text="만료된 과제 공고 본문"),
    ]


@pytest.fixture(params=["inmemory", "sqlite-bruteforce", "sqlite-vec"])
async def repo(request, tmp_path):
    if request.param == "inmemory":
        r = InMemoryRepository()
        r.today = lambda: TODAY
        yield r
        return
    from rra.adapters.persistence import SQLiteDocumentRepository

    if request.param == "sqlite-vec":
        pytest.importorskip("sqlite_vec")
    r = SQLiteDocumentRepository(
        tmp_path / "rra.sqlite",
        DeterministicEmbedding(),
        prefer_extension=request.param == "sqlite-vec",
        today=lambda: TODAY,
    )
    if r.backend.name != request.param.removeprefix("sqlite-"):  # pragma: no cover
        pytest.skip("벡터 백엔드 없음")
    yield r
    r.close()


@pytest.fixture
async def loaded(repo):
    await repo.upsert(docs(), chunks())
    return repo


def test_implements_port(repo):
    assert isinstance(repo, DocumentRepository)


async def test_get_document_round_trips_and_missing_is_none(loaded):
    got = await loaded.get_document("alio:1")
    assert got == docs()[0]
    assert got.visibility == "internal" and got.valid_until == date(2026, 12, 31)
    assert await loaded.get_document("nope:0") is None


async def test_upsert_is_idempotent_and_count_by_source_lists_only_present(loaded):
    await loaded.upsert(docs(), chunks())
    assert await loaded.count_by_source() == {"alio": 1, "openalex": 1, "ntis": 1}
    assert "kipris_kr" not in await loaded.count_by_source()


async def test_hybrid_search_returns_bounded_chunks_of_loaded_valid_documents(loaded):
    assert await loaded.hybrid_search([], k=5) == []
    assert await loaded.hybrid_search(["   "], k=5) == []
    hits = await loaded.hybrid_search(["궤도의 틀림을 자동으로 감지한다"], k=1)
    assert len(hits) <= 1 and all(isinstance(c, Chunk) for c in hits)
    all_hits = await loaded.hybrid_search(
        ["궤도의 틀림을 자동으로 감지한다", "IMU based track"], k=10
    )
    ids = {c.doc_id for c in all_hits}
    assert ids <= {"alio:1", "openalex:W1"} and "ntis:old" not in ids  # 만료 문서 제외
    assert all(c.chunk_id in {x.chunk_id for x in chunks()} for c in all_hits)


async def test_find_similar_ranks_identical_text_first_and_skips_expired(loaded):
    hits = await loaded.find_similar("궤도의 틀림을 자동으로 감지한다", k=5)
    assert hits and hits[0][0].doc_id == "alio:1"
    assert all(0.0 <= s <= 1.0 for _, s in hits) and len(hits) <= 5
    assert [s for _, s in hits] == sorted((s for _, s in hits), reverse=True)
    assert all(isinstance(d, Document) for d, _ in hits)
    expired = await loaded.find_similar("만료된 과제 공고 본문", k=5)
    assert "ntis:old" not in [d.doc_id for d, _ in expired]
    assert await loaded.find_similar("", k=5) == []
