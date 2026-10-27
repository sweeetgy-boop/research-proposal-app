"""TableSourcePort 어댑터 (P2-8) — 합성 스냅샷 + 가짜 runner(파일을 열지 않음), 판독 캐시, 문서
본문. 용어 후보 YAML 쓰기(P2-9)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from rra.adapters.sources._sandbox import ParseCrashed, SandboxLimits
from rra.adapters.sources.korail_web.snapshot import SnapshotDir
from rra.adapters.tables import DocumentTables, SnapshotTables, VisionTables
from rra.adapters.terms import write_candidates
from rra.adapters.vision.store import MemoryVisionStore
from rra.application.ports import TableSourcePort
from rra.domain.models import Document
from rra.domain.rules.table_facts import facts_of
from tests.fakes import InMemoryRepository
from tests.vision_helpers import TABLE_READING

LIMITS = SandboxLimits(timeout_sec=5, mem_mb=256, max_input_mb=1)
XLSX_MAGIC = b"PK\x03\x04" + b"\x00" * 60  # open_validated 는 매직만 본다 (파싱은 가짜 runner)
PDF_MAGIC = b"%PDF-1.7\n" + b"x" * 60
SHEETS = {
    "sheets": [
        {
            "name": "현황",
            "rows": [
                ["역별 승강설비 현황"],
                ["연 번", "노선명", "역 명", "엘리베이터", "에스컬레이터"],
                ["1", "경부선", "서울역사", "18", "23"],
            ],
        },
        {"name": "빈시트", "rows": []},
    ]
}
PAGES = {
    "pages": ["표지 (숫자 없음)", "(단위: 억원)\n구분 2023 2024\n매출액 5,100 5,300\n", "글만"]
}


def snapshot(tmp_path: Path, day="2026-10-27") -> SnapshotDir:
    snap = SnapshotDir(tmp_path / "korail_web", day)
    snap.ensure()
    snap.write_bytes("files/aa/aaaa.xlsx", XLSX_MAGIC)
    snap.write_bytes("files/bb/bbbb.pdf", PDF_MAGIC)
    snap.write_bytes("files/cc/cccc.hwp", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"x" * 64)
    base = {"menu_path": "정보공개", "doc_type": "policy", "snapshot": day, "removed": False}
    snap.append_manifest(
        {
            **base,
            "native_id": "preinfo:1",
            "title": "역별 승강설비 현황",
            "attachments": [
                {
                    "name": "역별 승강설비 현황.xlsx",
                    "ext": "xlsx",
                    "downloaded": True,
                    "path": "files/aa/aaaa.xlsx",
                    "sha256": "aaaa",
                },
                {
                    "name": "보고서.pdf",
                    "ext": "pdf",
                    "downloaded": True,
                    "path": "files/bb/bbbb.pdf",
                    "sha256": "bbbb",
                },
                {
                    "name": "한글.hwp",
                    "ext": "hwp",
                    "downloaded": True,
                    "path": "files/cc/cccc.hwp",
                    "sha256": "cccc",
                },
                {
                    "name": "안 받음.xlsx",
                    "ext": "xlsx",
                    "downloaded": False,
                    "path": "",
                    "sha256": "dddd",
                },
            ],
        }
    )
    snap.append_manifest(
        {
            **base,
            "native_id": "preinfo:2",
            "title": "같은 파일 다시",
            "attachments": [
                {
                    "name": "역별 승강설비 현황.xlsx",
                    "ext": "xlsx",
                    "downloaded": True,
                    "path": "files/aa/aaaa.xlsx",
                    "sha256": "aaaa",
                },
            ],
        },
    )
    snap.append_manifest(
        {**base, "native_id": "preinfo:3", "title": "삭제됨", "removed": True, "attachments": []}
    )
    return snap


class FakeRunner:
    def __init__(self, fail: set[str] | None = None):
        self.calls: list[str] = []
        self.fail = fail or set()

    async def __call__(self, fd, fmt, limits):
        self.calls.append(fmt)
        if fmt in self.fail:
            raise ParseCrashed("crashed")
        return SHEETS if fmt in ("xlsx", "xls") else PAGES


async def test_snapshot_tables_sheets_and_pdf_pages(tmp_path):
    snap = snapshot(tmp_path)
    runner = FakeRunner()
    source = SnapshotTables(snap.root, limits=LIMITS, runner=runner)
    assert isinstance(source, TableSourcePort) and source.name == "korail_web"
    tables = await source.tables()
    # xlsx: 시트 1개(빈 시트 제외), 같은 sha 는 한 번만. pdf: 숫자 있는 쪽 1개. hwp·미수신은 없음
    assert runner.calls == ["xlsx", "pdf_pages"]
    assert [(t.sheet, t.page) for t in tables] == [("현황", None), (None, 2)]
    sheet, page = tables
    assert sheet.doc_id.startswith("korail_web:") and len(sheet.doc_id) == len("korail_web:") + 16
    assert sheet.rows[1][3] == "엘리베이터" and sheet.title == "역별 승강설비 현황.xlsx 현황"
    assert page.lines == ["(단위: 억원)", "구분 2023 2024", "매출액 5,100 5,300"]
    facts = facts_of(page)
    assert [(f.item, f.year, f.unit) for f in facts] == [
        ("매출액", 2023, "억원"),
        ("매출액", 2024, "억원"),
    ]
    assert facts[0].page == 2 and facts[0].doc_id == page.doc_id


async def test_snapshot_tables_limit_explicit_day_and_rejections(tmp_path):
    snap = snapshot(tmp_path)
    assert (
        await SnapshotTables(
            snap.root, limits=LIMITS, snapshot="2020-01-01", runner=FakeRunner()
        ).tables()
        == []
    )
    runner = FakeRunner(fail={"pdf_pages"})
    tables = await SnapshotTables(
        snap.root, limits=LIMITS, snapshot="2026-10-27", runner=runner
    ).tables()
    assert [t.sheet for t in tables] == ["현황"]  # 샌드박스 실패는 건너뛴다 (경로·내용 없는 경고만)
    assert (
        len(await SnapshotTables(snap.root, limits=LIMITS, runner=FakeRunner()).tables(limit=1))
        == 1
    )
    assert await SnapshotTables(tmp_path / "없음", limits=LIMITS).tables() == []


async def test_vision_tables_only_confirmed_table_readings():
    store = MemoryVisionStore()
    sha_ok, sha_bad, sha_diag, sha_fail = "a" * 64, "b" * 64, "c" * 64, "d" * 64
    store.put_reading(sha_ok, {"ok": True, "reading": TABLE_READING})
    store.put_reading(sha_bad, {"ok": True, "reading": TABLE_READING})
    store.put_reading(
        sha_diag, {"ok": True, "reading": {**TABLE_READING, "image_type": "체계도·조직도·흐름도"}}
    )
    store.put_reading(sha_fail, {"ok": False, "error": "LLMError"})
    repo = InMemoryRepository()
    repo.seed(
        [
            Document(
                doc_id=f"korail_web:img:{sha_bad[:16]}",
                source="korail_web",
                doc_type="web_page",
                title="표",
                text_basis="image_vision",
                raw={"image": {"unconfirmed_numbers": ["1,300만명"]}},
            ),
        ],
        [],
    )
    source = VisionTables(store, repo)
    assert isinstance(source, TableSourcePort) and source.name == "vision"
    tables = await source.tables()
    assert [t.doc_id for t in tables] == [f"korail_web:img:{sha_ok[:16]}"]
    assert tables[0].basis == "image_vision" and tables[0].title == "수송 실적"
    assert source.skipped == {"unconfirmed_numbers": 1}
    facts = facts_of(tables[0])
    assert {(f.item, f.year, f.unit) for f in facts} == {
        ("수송인원", 2023, "만명"),
        ("수송인원", 2024, "만명"),
        ("증가율", 2023, "%"),
        ("증가율", 2024, "%"),
    }
    assert all(f.basis == "image_vision" for f in facts)
    assert await VisionTables(store, repo).tables(limit=0) == []


async def test_document_tables_from_bodies():
    repo = InMemoryRepository()
    repo.seed(
        [
            Document(
                doc_id="molit:1",
                source="molit",
                doc_type="policy",
                title="투자",
                body="구분 2023 2024\n예산 5,100 5,300",
            ),
            Document(
                doc_id="molit:2",
                source="molit",
                doc_type="policy",
                title="글",
                body="숫자 없는 본문",
            ),
            Document(
                doc_id="alio:3",
                source="alio",
                doc_type="internal_report",
                title="x",
                body="2023 1 2",
            ),
        ],
        [],
    )
    source = DocumentTables(repo, source="molit")
    assert isinstance(source, TableSourcePort) and source.name == "molit"
    tables = await source.tables()
    assert [t.doc_id for t in tables] == ["molit:1"] and tables[0].page is None
    assert [(f.item, f.year) for f in facts_of(tables[0])] == [("예산", 2023), ("예산", 2024)]


def test_write_candidates_yaml(tmp_path):
    payloads = {
        "rail_terms.candidates.yaml": {
            "kind": "rail_terms",
            "candidates": [{"term": "궤도", "doc_freq": 2}],
        },
        "generic_terms.candidates.yaml": {"kind": "generic_terms", "candidates": []},
    }
    written = write_candidates(tmp_path / "config", payloads)
    assert [p.name for p in written] == list(payloads)
    text = written[0].read_text(encoding="utf-8")
    assert text.startswith("# 자동 생성된 후보 목록") and "자동 반영되지 않는다" in text
    assert yaml.safe_load(text) == payloads["rail_terms.candidates.yaml"]
    assert "궤도" in text  # allow_unicode — 이스케이프 없이 읽을 수 있다
    with pytest.raises(ValueError):
        write_candidates(tmp_path, {"../x.yaml": {}})
