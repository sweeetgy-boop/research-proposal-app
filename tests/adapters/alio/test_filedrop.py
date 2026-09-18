"""알리오 filedrop — 검증·격리·로그 비노출·acknowledge. 파서는 실제 샌드박스 또는 가짜 runner."""

import logging

import pytest

from rra.adapters.sources._sandbox import ParseCrashed, ParseTimeout
from rra.adapters.sources.alio.filedrop import AlioSource, inbox_status, normalize_report
from rra.application.usecases.ingest_sources import IngestSources
from rra.domain.models import CatalogEntry
from tests.fakes import FakeCatalog, InMemoryRepository

from .conftest import make_hwpx, make_pdf

HIDDEN_NAME = "기밀_코레일_보고서"


@pytest.fixture
def inbox(tmp_path):
    d = tmp_path / "inbox"
    d.mkdir()
    return d


def ok_runner(text="제목 줄\n본문"):
    calls = []

    async def run(fd, fmt, limits):
        calls.append(fmt)
        return {"text": text, "toc": [], "pages": 1}

    run.calls = calls
    return run


def failing_runner(exc):
    async def run(fd, fmt, limits):
        raise exc

    return run


def entry(cid="2024-117"):
    return CatalogEntry(catalog_id=cid, institution_tag="korail", title="궤도 틀림 연구")


# ── search ───────────────────────────────────────────────
async def test_valid_file_becomes_raw_with_catalog_match(inbox, limits):
    (inbox / "2024-117.pdf").write_bytes(b"%PDF-1.7 fake")
    src = AlioSource(inbox, limits=limits, catalog=FakeCatalog([entry()]), runner=ok_runner())
    [raw] = await src.search(None, 10)
    assert raw["fmt"] == "pdf" and raw["catalog"]["catalog_id"] == "2024-117"
    doc = src.normalize(raw)
    assert doc.doc_id == "alio:2024-117" and doc.orgs == ["korail"]
    assert doc.title == "궤도 틀림 연구" and doc.body == "제목 줄\n본문"
    assert (inbox / "2024-117.pdf").exists()  # acknowledge 전에는 옮기지 않는다


async def test_limit_and_hidden_and_underscore_entries_skipped(inbox, limits):
    for name in ("a.pdf", "b.pdf", "c.pdf", ".DS_Store", "_note.pdf"):
        (inbox / name).write_bytes(b"%PDF-1.7")
    (inbox / "_done").mkdir()
    runner = ok_runner()
    raws = await AlioSource(inbox, limits=limits, runner=runner).search(None, 2)
    assert len(raws) == 2 and runner.calls == ["pdf", "pdf"]


@pytest.mark.parametrize(
    ("name", "body", "runner", "error"),
    [
        (f"{HIDDEN_NAME}.pdf", b"PK\x03\x04", ok_runner(), "MagicMismatch"),
        (
            f"{HIDDEN_NAME}.hwp",
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
            ok_runner(),
            "UnsupportedFormat",
        ),
        (f"{HIDDEN_NAME}.exe", b"MZ", ok_runner(), "BadExtension"),
        (f"{HIDDEN_NAME}.pdf", b"%PDF-", failing_runner(ParseTimeout("t")), "ParseTimeout"),
        (f"{HIDDEN_NAME}.pdf", b"%PDF-", failing_runner(ParseCrashed("c")), "ParseCrashed"),
        (f"{HIDDEN_NAME}.pdf", b"%PDF-", ok_runner(text="  \n "), "NoTextLayer"),
    ],
)
async def test_rejected_file_quarantined_and_log_has_only_class_name(
    inbox, limits, caplog, name, body, runner, error
):
    (inbox / name).write_bytes(body)
    with caplog.at_level(logging.WARNING, logger="rra.sources.alio"):
        assert await AlioSource(inbox, limits=limits, runner=runner).search(None, 10) == []

    assert not (inbox / name).exists()
    assert len(list((inbox / "_quarantine").iterdir())) == 1
    [record] = caplog.records
    message = record.getMessage()
    assert f"error={error}" in message
    assert HIDDEN_NAME not in message and str(inbox) not in message
    assert record.exc_info is None  # 트레이스백(파일 경로 포함 가능)도 남기지 않는다


async def test_real_sandbox_rejection_reason_is_child_class_name(inbox, limits, caplog):
    (inbox / f"{HIDDEN_NAME}.hwpx").write_bytes(make_hwpx(extra={"../evil": b"x"}))
    with caplog.at_level(logging.WARNING, logger="rra.sources.alio"):
        await AlioSource(inbox, limits=limits).search(None, 10)
    [record] = caplog.records
    assert "error=UnsafeArchive file=sha256:" in record.getMessage()
    assert HIDDEN_NAME not in record.getMessage()


async def test_broken_catalog_does_not_stop_files(inbox, limits, caplog):
    class Broken:
        async def entries(self):
            raise OSError("/secret/catalog.csv")

    (inbox / "a.pdf").write_bytes(b"%PDF-1.7")
    with caplog.at_level(logging.WARNING, logger="rra.sources.alio"):
        raws = await AlioSource(inbox, limits=limits, catalog=Broken(), runner=ok_runner()).search(
            None, 10
        )
    assert len(raws) == 1 and raws[0]["catalog"] is None
    assert "secret" not in caplog.text and "error=OSError" in caplog.text


# ── 유스케이스까지 (실제 샌드박스, PDF·HWPX) ─────────────
async def test_ingest_end_to_end_moves_to_done(inbox, limits):
    (inbox / "2024-117.pdf").write_bytes(make_pdf(["1. 서론\n궤도 틀림 감지"]))
    (inbox / "unmatched.hwpx").write_bytes(make_hwpx())
    (inbox / "bad.pdf").write_bytes(b"PK\x03\x04")
    repo = InMemoryRepository()
    src = AlioSource(inbox, limits=limits, catalog=FakeCatalog([entry()]))

    report = await IngestSources([src], repo)()

    assert report.stored == 2 and report.failed == {}
    assert set(repo.docs) >= {"alio:2024-117"}
    unmatched = next(d for d in repo.docs.values() if d.doc_id.startswith("alio:sha-"))
    assert unmatched.title == "제1장 서론" and unmatched.raw["catalog_matched"] is False
    assert inbox_status(inbox) == {"pending": 0, "done": 2, "quarantine": 1}


async def test_upsert_failure_leaves_files_in_inbox(inbox, limits):
    class BrokenRepo(InMemoryRepository):
        def upsert(self, docs, chunks):
            raise RuntimeError("db locked")

    (inbox / "a.pdf").write_bytes(b"%PDF-1.7")
    src = AlioSource(inbox, limits=limits, runner=ok_runner())
    with pytest.raises(RuntimeError):
        await IngestSources([src], BrokenRepo())()
    assert inbox_status(inbox) == {"pending": 1, "done": 0, "quarantine": 0}


# ── normalize_report (순수) ──────────────────────────────
def test_normalize_title_fallbacks():
    base = {"sha256": "ab" * 32, "fmt": "pdf", "catalog": None}
    meta = normalize_report({**base, "extract": {"text": "첫 줄\n둘째", "meta_title": "메타 제목"}})
    assert meta.title == "메타 제목" and meta.doc_id == "alio:sha-" + "ab" * 8
    first = normalize_report({**base, "extract": {"text": "\n\n  첫 줄\x1b  \n둘째"}})
    assert first.title == "첫 줄"
    assert first.raw == {
        "sha256": "ab" * 32,
        "fmt": "pdf",
        "catalog_id": None,
        "catalog_matched": False,
        "pages": None,
        "truncated": False,
    }


def test_normalize_rejects_empty_text():
    with pytest.raises(ValueError):
        normalize_report({"sha256": "0" * 64, "catalog": None, "extract": {"text": " "}})
