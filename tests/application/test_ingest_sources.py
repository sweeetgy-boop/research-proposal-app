"""ingest_sources 유스케이스 — fake 만으로 실행 (네트워크·임베딩 없음)."""

from rra.application.usecases.ingest_sources import IngestSources
from tests.fakes import FakeSource, InMemoryRepository


class RecordingRepository(InMemoryRepository):
    def __init__(self):
        super().__init__()
        self.upserts = []

    def upsert(self, docs, chunks):
        self.upserts.append((list(docs), list(chunks)))
        super().upsert(docs, chunks)


def as_raw(doc):
    return doc.model_dump(mode="json")


async def test_dedup_then_chunk_then_single_upsert(docs):
    # conftest: openalex:W1 과 scienceon:9 는 DOI 대소문자만 다른 같은 논문
    repo = RecordingRepository()
    sources = [
        FakeSource("alio", [as_raw(docs[0])]),
        FakeSource("openalex", [as_raw(docs[1])]),
        FakeSource("scienceon", [as_raw(docs[2])]),
    ]
    report = await IngestSources(sources, repo)()

    assert len(repo.upserts) == 1
    stored, chunks = repo.upserts[0]
    assert [d.doc_id for d in stored] == ["alio:1", "openalex:W1"]
    # 청크는 dedup 을 통과한 문서에서만 나온다
    assert {c.doc_id for c in chunks} == {"alio:1", "openalex:W1"}
    assert [c.heading for c in chunks if c.doc_id == "alio:1"] == ["1장 서론", "2장 방법"]
    assert report.deduped == 1
    assert report.stored == 2
    assert report.chunks == len(chunks)


async def test_passes_query_and_limit_to_every_source(docs):
    a, b = FakeSource("openalex", [as_raw(docs[1])]), FakeSource("alio", [as_raw(docs[0])])
    await IngestSources([a, b], InMemoryRepository(), limit=7)("궤도")
    assert a.calls == [("궤도", 7)]
    assert b.calls == [("궤도", 7)]


async def test_incremental_run_passes_none(docs):
    src = FakeSource("openalex", [as_raw(docs[1])])
    await IngestSources([src], InMemoryRepository())()
    assert src.calls == [(None, 200)]


async def test_broken_record_is_skipped_not_fatal(docs):
    broken = {"doc_id": "openalex:W2", "source": "openalex"}  # doc_type·title 없음
    repo = RecordingRepository()
    report = await IngestSources([FakeSource("openalex", [broken, as_raw(docs[1])])], repo)()

    assert report.fetched == {"openalex": 2}
    assert report.normalized == {"openalex": 1}
    assert report.skipped == {"openalex": 1}
    assert [d.doc_id for d in repo.upserts[0][0]] == ["openalex:W1"]


async def test_failing_source_is_isolated_and_error_text_not_kept(docs):
    repo = RecordingRepository()
    sources = [FakeSource("scienceon", [], fail=True), FakeSource("alio", [as_raw(docs[0])])]
    report = await IngestSources(sources, repo)()

    assert report.failed == {"scienceon": "RuntimeError"}  # 메시지(URL·키)는 남기지 않는다
    assert "SECRET" not in repr(report)
    assert report.stored == 1
    assert [d.doc_id for d in repo.upserts[0][0]] == ["alio:1"]


async def test_nothing_fetched_means_no_upsert():
    repo = RecordingRepository()
    report = await IngestSources([FakeSource("openalex", [])], repo)()
    assert repo.upserts == []
    assert report.stored == 0 and report.chunks == 0
