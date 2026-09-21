"""ingest_sources 유스케이스 — fake 만으로 실행 (네트워크·임베딩 없음)."""

import pytest

from rra.application.usecases.ingest_sources import IngestSources, IngestWarning
from tests.fakes import FakeAckSource, FakeSource, InMemoryRepository


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


# ── acknowledge (filedrop 처리 완료 통보) ─────────────────
async def test_acknowledge_only_normalized_raws_after_upsert(docs):
    broken = {"doc_id": "alio:2", "source": "alio"}
    src = FakeAckSource("alio", [as_raw(docs[0]), broken])
    repo = RecordingRepository()
    await IngestSources([src], repo)()
    assert len(repo.upserts) == 1
    assert [r["doc_id"] for r in src.acked] == ["alio:1"]


async def test_no_acknowledge_when_upsert_fails(docs):
    class BrokenRepo(InMemoryRepository):
        def upsert(self, docs, chunks):
            raise RuntimeError("disk full")

    src = FakeAckSource("alio", [as_raw(docs[0])])
    with pytest.raises(RuntimeError):
        await IngestSources([src], BrokenRepo())()
    assert src.acked == []


async def test_plain_source_is_not_acknowledged(docs):
    src = FakeSource("openalex", [as_raw(docs[1])])
    report = await IngestSources([src], InMemoryRepository())()
    assert report.failed == {}


async def test_summary_does_not_overwrite_stored_full_text(docs):
    full = docs[0]  # alio:1, text_basis=full_text
    summary = full.model_copy(update={"text_basis": "summary", "body": "공개 요약 " * 50})
    repo = RecordingRepository()
    repo.upsert([full], [])
    src = FakeAckSource("alio_summary", [as_raw(summary)])
    report = await IngestSources([src], repo)()

    assert report.stored == 0 and report.kept_existing == 1
    assert repo.get_document("alio:1").text_basis == "full_text"
    assert len(repo.upserts) == 1  # 사전 적재 1회뿐
    assert src.acked == [as_raw(summary)]  # 더 나은 판본이 있으니 처리 완료


async def test_full_text_replaces_stored_summary(docs):
    full = docs[0]
    summary = full.model_copy(update={"text_basis": "summary"})
    repo = RecordingRepository()
    repo.upsert([summary], [])
    report = await IngestSources([FakeSource("alio", [as_raw(full)])], repo)()
    assert report.stored == 1 and report.kept_existing == 0
    assert repo.get_document("alio:1").text_basis == "full_text"


async def test_warns_on_own_org_department_not_in_list(docs, own, caplog):
    import logging

    unknown = docs[0].model_copy(
        update={"doc_id": "alio:2", "title": "다른 보고서", "department": "신규\x1b[31m연구처"}
    )
    listed = docs[0].model_copy(update={"department": "경영연구처"})
    src = FakeSource("alio", [as_raw(unknown), as_raw(listed), as_raw(docs[1])])
    with caplog.at_level(logging.WARNING, logger="rra.ingest"):
        report = await IngestSources([src], RecordingRepository(), own=own)()

    assert report.warnings == [
        IngestWarning(code="unlisted_department", doc_id="alio:2", detail="신규 [31m연구처")
    ]
    [record] = caplog.records
    message = record.getMessage()
    assert "ingest.unlisted_department doc=alio:2" in message and "\x1b" not in message


async def test_no_department_warning_without_own_unit(docs):
    report = await IngestSources([FakeSource("alio", [as_raw(docs[0])])], RecordingRepository())()
    assert report.warnings == []


class WarningFakeSource(FakeSource):
    """WarningSource fake: 제목에 '추정' 이 있으면 assumed_org 경고."""

    def ingest_warnings(self, doc):
        return [("assumed_org", "korail")] if "추정" in doc.title else []


async def test_source_warnings_reported_only_for_stored_docs(docs):
    guessed = docs[0].model_copy(update={"doc_id": "alio:sum-1", "title": "추정 기관 요약"})
    plain = docs[0].model_copy(update={"doc_id": "alio:sum-2", "title": "매칭된 요약"})
    # 같은 제목의 원문이 이미 저장돼 있으면 요약은 저장되지 않으므로 경고도 없다
    stored_full = docs[0].model_copy(update={"doc_id": "alio:sum-3", "title": "추정 원문 있음"})
    lower = stored_full.model_copy(update={"text_basis": "summary"})
    repo = RecordingRepository()
    repo.upsert([stored_full], [])
    src = WarningFakeSource("alio_summary", [as_raw(guessed), as_raw(plain), as_raw(lower)])
    report = await IngestSources([src], repo)()

    assert report.kept_existing == 1
    assert report.warnings == [
        IngestWarning(code="assumed_org", doc_id="alio:sum-1", detail="korail")
    ]


async def test_broken_warning_source_does_not_block_ingest(docs):
    class Broken(FakeSource):
        def ingest_warnings(self, doc):
            raise RuntimeError("boom")

    report = await IngestSources([Broken("alio", [as_raw(docs[0])])], RecordingRepository())()
    assert report.stored == 1 and report.warnings == []
