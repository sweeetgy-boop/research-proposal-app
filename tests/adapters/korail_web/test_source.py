"""KorailWebSource — 스냅샷 → Document. 샌드박스는 가짜 runner 로 대체 (파일 열지 않음)."""

import json
from datetime import date
from pathlib import Path

import pytest

from rra.adapters.sources._sandbox import SandboxLimits
from rra.adapters.sources.korail_web import KorailWebSource, normalize_korail_item
from rra.adapters.sources.korail_web.snapshot import SnapshotDir
from rra.domain.models import Document
from rra.domain.rules.dedup import dedup

HWP = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"x" * 64
LONG = "코레일 중장기 경영목표. 모두가 안심하는 AX 철도안전 구축. " * 5


def _snapshot(tmp_path: Path, day="2026-10-27") -> SnapshotDir:
    snap = SnapshotDir(tmp_path / "korail_web", day)
    snap.ensure()
    snap.write_text("items/mgmt_goal/contents-1900.txt", LONG + "\n담당자 홍길동 과장 042-615-3647")
    snap.write_text("items/press/bbs-199-1.txt", "짧음")
    snap.write_bytes("files/ab/abcd.hwp", HWP)
    base = {
        "menu_path": "ESG경영 > 경영공시 > 일반항목 > 중장기 경영목표",
        "doc_type": "policy",
        "terms": "공공누리 제4유형",
        "snapshot": day,
        "removed": False,
    }
    snap.append_manifest(
        {
            **base,
            "native_id": "contents:1900",
            "menu": "mgmt_goal",
            "title": "중장기 경영목표",
            "url": "https://info.korail.com/info/contents.do?key=1900",
            "text_file": "items/mgmt_goal/contents-1900.txt",
            "text_sha256": "a" * 64,
            "attachments": [
                {
                    "name": "261001_(사전정보공표) 경영목표 요약.hwp",
                    "url": "https://info.korail.com/info/downloadBbsFile.do?atchmnflNo=1",
                    "ext": "hwp",
                    "downloaded": True,
                    "path": "files/ab/abcd.hwp",
                    "sha256": "abcd",
                    "snapshot": day,
                },
                {
                    "name": "photo.jpg",
                    "url": "https://info.korail.com/info/downloadBbsFile.do?atchmnflNo=2",
                    "ext": "jpg",
                    "downloaded": False,
                    "reason": "policy_images",
                },
            ],
            "images": [],
        }
    )
    snap.append_manifest(
        {
            **base,
            "native_id": "bbs:199:1",
            "menu": "press",
            "menu_path": "홍보센터 > 홍보 > 보도자료",
            "doc_type": "korail_news",
            "title": "짧은 글",
            "url": "https://info.korail.com/info/selectBbsNttView.do?nttNo=1",
            "text_file": "items/press/bbs-199-1.txt",
            "text_sha256": "b" * 64,
            "posted": "2026-10-22",
            "attachments": [],
            "images": [],
        }
    )
    snap.append_manifest(
        {
            **base,
            "native_id": "bbs:199:2",
            "menu": "press",
            "doc_type": "korail_news",
            "title": "사라진 글",
            "url": "https://info.korail.com/x",
            "text_file": "items/mgmt_goal/contents-1900.txt",
            "text_sha256": "a" * 64,
            "attachments": [],
            "images": [],
            "removed": True,
            "note": "원본 삭제됨",
        }
    )
    # 같은 첨부가 다른 메뉴에도 (중복 제거 확인)
    snap.append_manifest(
        {
            **base,
            "native_id": "contents:2490",
            "menu": "preinfo_freq",
            "menu_path": "정보공개 > 자주찾는",
            "title": "자주찾는",
            "url": "https://info.korail.com/info/contents.do?key=2490",
            "text_file": "items/none.txt",
            "text_sha256": "c" * 64,
            "attachments": [
                {
                    "name": "경영목표 요약.hwp",
                    "url": "https://info.korail.com/info/downloadContentsFile.do?key=2490&fileNo=1",
                    "ext": "hwp",
                    "downloaded": True,
                    "path": "files/ab/abcd.hwp",
                    "sha256": "abcd",
                    "snapshot": day,
                }
            ],
            "images": [],
        }
    )
    return snap


async def fake_runner(fd: int, fmt: str, limits: SandboxLimits) -> dict:
    assert fmt == "hwp"
    return {
        "text": "요약 본문입니다. 연락처 010-1234-5678 로 문의. " * 6,
        "toc": ["1. 개요"],
        "pages": 2,
    }


async def test_search_reads_latest_snapshot_dedups_and_skips_removed_and_short(tmp_path):
    _snapshot(tmp_path)
    src = KorailWebSource(tmp_path / "korail_web", limits=SandboxLimits(), runner=fake_runner)
    raws = await src.search(None, 100)
    kinds = [(r["kind"], r["native_id"]) for r in raws]
    assert kinds == [("page", "contents:1900"), ("attachment", "contents:1900")]
    att = raws[1]
    assert att["also_in"] == ["정보공개 > 자주찾는"]  # 같은 sha256 첨부는 한 번만
    assert (
        src.status()["snapshot"] == "2026-10-27"
        and src.status()["items"] == 3
        and src.status()["removed"] == 1
    )


async def test_normalize_strips_pii_and_sets_metadata(tmp_path):
    _snapshot(tmp_path)
    src = KorailWebSource(tmp_path / "korail_web", limits=SandboxLimits(), runner=fake_runner)
    raws = await src.search(None, 100)
    page = src.normalize(raws[0])
    assert isinstance(page, Document)
    assert page.source == "korail_web" and page.doc_type == "policy" and page.visibility == "public"
    assert page.doc_id == "korail_web:" + "a" * 16 and page.title == "중장기 경영목표"
    assert "홍길동" not in page.body and "042" not in page.body and "[이름 삭제]" in page.body
    assert page.orgs == ["korail"] and page.text_basis == "full_text"
    assert page.raw["crawl_snapshot"] == "2026-10-27" and page.raw["menu_path"].startswith(
        "ESG경영"
    )
    assert page.raw["terms"] == "공공누리 제4유형" and page.url.endswith("key=1900")
    att = src.normalize(raws[1])
    assert (
        att.title == "경영목표 요약" and att.raw["kind"] == "attachment" and att.raw["fmt"] == "hwp"
    )
    assert "010" not in att.body and att.toc == ["1. 개요"] and att.raw["pages"] == 2
    assert att.doc_id != page.doc_id
    assert src.ingest_warnings(att) == []
    assert len(dedup([page, att])) == 2


def test_normalize_rejects_other_doc_types_and_empty_text():
    with pytest.raises(ValueError):
        normalize_korail_item({"text": "x", "sha256": "1" * 64, "doc_type": "paper"})
    with pytest.raises(ValueError):
        normalize_korail_item({"text": "   ", "sha256": "1" * 64, "doc_type": "policy"})


def test_normalize_news_with_date():
    doc = normalize_korail_item(
        {
            "kind": "page",
            "text": "보도자료 본문",
            "sha256": "f" * 64,
            "doc_type": "korail_news",
            "title": "제목",
            "posted": "2026-10-22",
            "snapshot": "2026-10-27",
            "url": "https://info.korail.com/x",
        }
    )
    assert doc.doc_type == "korail_news" and doc.pub_date == date(2026, 10, 22)


def test_no_text_layer_warning():
    doc = normalize_korail_item(
        {
            "kind": "attachment",
            "text": "스캔",
            "sha256": "e" * 64,
            "doc_type": "policy",
            "title": "scan.pdf",
            "text_layer": False,
            "fmt": "pdf",
        }
    )
    src = KorailWebSource(Path("/nonexistent"), limits=SandboxLimits())
    assert src.ingest_warnings(doc) == [("no_text_layer", "scan.pdf")]
    assert src.status() == {"snapshot": None, "items": 0}


def test_manifest_lines_are_json(tmp_path):
    snap = _snapshot(tmp_path)
    lines = snap.manifest.read_text(encoding="utf-8").splitlines()
    assert all(json.loads(line)["native_id"] for line in lines)


async def _sheet_runner(fd: int, fmt: str, limits: SandboxLimits) -> dict:
    assert fmt == "xlsx"
    rows = [["구분", "2023", "2024"]] + [[f"항목{i}", i * 10, i * 11] for i in range(12)]
    return {"sheets": [{"name": "수송실적", "rows": rows}]}


async def test_xlsx_attachment_is_ingested_as_pipe_rows(tmp_path):
    day = "2026-10-27"
    snap = SnapshotDir(tmp_path / "korail_web", day)
    snap.ensure()
    snap.write_bytes("files/ab/abcd.xlsx", b"PK\x03\x04" + b"0" * 200)
    snap.append_manifest(
        {
            "native_id": "biz:1",
            "menu": "biz_stat_docs",
            "menu_path": "주요사업 > 광역수송",
            "doc_type": "statistics",
            "terms": "공공누리 제4유형",
            "snapshot": day,
            "removed": False,
            "title": "광역수송 통계",
            "url": "https://info.korail.com/x",
            "text_file": None,
            "posted": "2026-01-01",
            "attachments": [
                {
                    "name": "수송실적.xlsx",
                    "url": "https://info.korail.com/f/1",
                    "ext": "xlsx",
                    "downloaded": True,
                    "path": "files/ab/abcd.xlsx",
                    "sha256": "abcd",
                    "snapshot": day,
                }
            ],
            "images": [],
        }
    )
    src = KorailWebSource(tmp_path / "korail_web", limits=SandboxLimits(), runner=_sheet_runner)
    raws = await src.search(None, 100)
    att = [r for r in raws if r["kind"] == "attachment"]
    assert len(att) == 1
    assert att[0]["text"].startswith("[수송실적]\n구분 | 2023 | 2024\n항목0 | 0 | 0")
