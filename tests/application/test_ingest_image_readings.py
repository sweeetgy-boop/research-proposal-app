"""P3 ⑥ 판독 캐시 → 적재 — 호출 없음, 페이지 문서 조회, dry-run 은 upsert 없음. 페이크 저장소."""

import pytest

from rra.adapters.vision.store import MemoryVisionStore
from rra.application.usecases.ingest_image_readings import IngestImageReadings
from rra.application.usecases.read_images import ReadImages
from rra.domain.models import Document
from rra.entrypoints.cli import EXIT_OK, main
from tests.vision_helpers import (
    TABLE_READING,
    FakeOcr,
    FakeReader,
    item,
    sha,
    snapshot_of,
    table_image,
)

PAGE = Document(
    doc_id="alio:page-1",
    source="alio",
    doc_type="internal_report",
    title="수송 통계",
    body="페이지 본문",
    visibility="public",
)


class FakeRepo:
    def __init__(self, docs=None):
        self.docs = {d.doc_id: d for d in docs or []}
        self.upserts = []

    async def get_document(self, doc_id):
        return self.docs.get(doc_id)

    async def upsert(self, docs, chunks):
        self.upserts.append((docs, chunks))


def cache_only_reader(store, page_doc_id="alio:page-1"):
    table = table_image()
    snap = snapshot_of((table, item(table, "stat/t.png", page_doc_id=page_doc_id)))
    return ReadImages(
        snap, store, ocr=FakeOcr({sha(table): "수송인원 1,234만명"}), reader=None, prompt="V"
    )


async def test_ingests_cached_readings_as_image_vision_documents():
    store = MemoryVisionStore()
    table = table_image()
    store.put_reading(sha(table), {"ok": True, "reading": TABLE_READING})
    repo = FakeRepo([PAGE])
    report = await IngestImageReadings(cache_only_reader(store), repo)()

    assert report.summary() == {
        "snapshot": "2026-10-27",
        "dry_run": False,
        "results": 1,
        "documents": 1,
        "chunks": 1,
        "skipped": {},
        "removed_personal": {},
        "pages_found": 1,
    }
    docs, chunks = repo.upserts[0]
    assert docs[0].doc_id == f"alio:img:{sha(table)[:16]}" and docs[0].text_basis == "image_vision"
    assert (
        docs[0].raw["image"]["page_doc_id"] == "alio:page-1" and chunks[0].basis == "image_vision"
    )
    assert report.doc_ids == [docs[0].doc_id]


async def test_dry_run_does_not_upsert_and_unknown_source_is_skipped():
    store = MemoryVisionStore()
    store.put_reading(sha(table_image()), {"ok": True, "reading": TABLE_READING})
    repo = (
        FakeRepo()
    )  # 페이지 문서 없음 → manifest source(korail_web) 를 그대로 따른다 (크롤 레인 병합 뒤)
    report = await IngestImageReadings(cache_only_reader(store), repo)(dry_run=True)
    assert report.dry_run and repo.upserts == [] and report.skipped == {}
    assert report.doc_ids and report.doc_ids[0].startswith("korail_web:img:")


def test_requires_cache_only_reader():
    with pytest.raises(ValueError):
        IngestImageReadings(
            ReadImages(
                snapshot_of(), MemoryVisionStore(), ocr=None, reader=FakeReader(), prompt="V"
            ),
            FakeRepo(),
        )


def test_cli_ingest_dry_run(monkeypatch, capsys):
    store = MemoryVisionStore()
    store.put_reading(sha(table_image()), {"ok": True, "reading": TABLE_READING})
    usecase = IngestImageReadings(cache_only_reader(store), FakeRepo([PAGE]))
    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr("rra.composition.build_ingest_image_readings", lambda s, **kw: usecase)
    assert main(["vision", "ingest", "--dry-run"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "문서 1건 / 청크 1건" in out and "dry-run" in out
