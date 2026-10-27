"""PDF·HWPX·CSV 추출 — 항상 샌드박스를 거쳐 실행 (악성 샘플이 본체에서 파싱되지 않음)."""

import os
import unicodedata
from pathlib import Path

import pytest

from rra.adapters.sources._sandbox import ParseRejected, run_parser
from rra.adapters.sources.alio.extract.hwpx import section_lines

from .conftest import BILLION_LAUGHS, SECTION_XML, XXE, make_hwpx, make_pdf, zip_bomb


@pytest.fixture
def parse(tmp_path, limits):
    async def run(data: bytes, fmt: str, lim=None):
        path = tmp_path / f"in.{fmt}"
        path.write_bytes(data)
        fd = os.open(path, os.O_RDONLY)
        try:
            return await run_parser(fd, fmt, lim or limits)
        finally:
            os.close(fd)

    return run


async def rejected(parse, data, fmt, lim=None) -> str:
    with pytest.raises(ParseRejected) as info:
        await parse(data, fmt, lim)
    return info.value.error


# ── HWPX ─────────────────────────────────────────────────
def test_section_lines_paragraphs_tabs_and_nested_tables():
    assert section_lines(SECTION_XML.encode()) == [
        "제1장 서론",
        "궤도 틀림\t자동 감지",
        "표 안 문단",
        "제2장 방법",
    ]


def test_section_lines_deep_nesting_does_not_recurse():
    deep = "<a>" * 5000 + "<t>x</t>" + "</a>" * 5000
    assert section_lines(deep.encode()) == ["x"]


async def test_hwpx_roundtrip(parse):
    result = await parse(
        make_hwpx({"Contents/section1.xml": SECTION_XML, "Contents/section0.xml": SECTION_XML}),
        "hwpx",
    )
    assert result["text"].count("제1장 서론") == 2
    assert result["truncated"] is False


@pytest.mark.parametrize(
    ("data", "error"),
    [
        (zip_bomb(), "ArchiveTooLarge"),
        (make_hwpx(extra={"../evil.xml": b"x"}), "UnsafeArchive"),
        (make_hwpx(extra={"/etc/evil": b"x"}), "UnsafeArchive"),
        (make_hwpx(extra={"C:/evil": b"x"}), "UnsafeArchive"),
        (make_hwpx(extra={"a\\..\\evil": b"x"}), "UnsafeArchive"),
        (make_hwpx(mimetype=b"application/zip"), "NotHwpx"),
        (make_hwpx({"Contents/other.xml": "<a/>"}), "NotHwpx"),
        (make_hwpx({"Contents/section0.xml": BILLION_LAUGHS}), "DTDForbidden"),
        (make_hwpx({"Contents/section0.xml": XXE}), "DTDForbidden"),
        (b"PK\x03\x04 not really a zip", "BadZipFile"),
    ],
    # id 를 이름으로 — zip 바이트는 프로세스마다 달라(시각) xdist 워커 간 수집이 어긋난다
    ids=[
        "zip_bomb",
        "dotdot",
        "absolute",
        "drive",
        "backslash",
        "mimetype",
        "no_section",
        "billion_laughs",
        "xxe",
        "not_zip",
    ],
)
async def test_malicious_hwpx_rejected_in_child(parse, data, error):
    assert await rejected(parse, data, "hwpx") == error


async def test_hwpx_entry_count_cap(parse, limits):
    from dataclasses import replace

    many = make_hwpx(extra={f"BinData/{i}.bin": b"x" for i in range(20)})
    assert await rejected(parse, many, "hwpx", replace(limits, max_zip_entries=10)) == (
        "ArchiveTooLarge"
    )


async def test_hwpx_declared_size_cap(parse, limits):
    from dataclasses import replace

    # 40KB 무작위 hex 블록 반복: deflate 창(32KB)보다 길어 압축비 ~2 → 압축비 검사는 통과,
    # 입력(~0.6MB)은 상한 1MB 이내지만 선언된 해제 크기(1.2MB)가 상한을 넘는다.
    body = os.urandom(20_000).hex().encode() * 30
    data = make_hwpx({"Contents/section0.xml": body})
    assert len(data) < 1024 * 1024 < len(body)
    assert await rejected(parse, data, "hwpx", replace(limits, max_input_mb=1)) == (
        "ArchiveTooLarge"
    )


# ── PDF ──────────────────────────────────────────────────
async def test_pdf_text_toc_and_metadata(parse):
    data = make_pdf(["1. 서론\n궤도 틀림 감지", "2. 방법\n가속도 센서"], title="철도 보고서")
    result = await parse(data, "pdf")
    assert "궤도 틀림 감지" in result["text"] and "가속도 센서" in result["text"]
    assert result["toc"] == ["1. 서론", "2. 방법"]
    assert result["pages"] == 2
    assert result["meta_title"] == "철도 보고서"


async def test_pdf_page_cap(parse, limits):
    from dataclasses import replace

    data = make_pdf([f"p{i}" for i in range(5)], toc=False)
    assert await rejected(parse, data, "pdf", replace(limits, max_pdf_pages=3)) == "TooManyPages"


async def test_pdf_encrypted_rejected(parse):
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secret")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
    assert await rejected(parse, data, "pdf") == "EncryptedDocument"


async def test_pdf_garbage_rejected(parse):
    assert await rejected(parse, b"%PDF-1.7\n" + os.urandom(2048), "pdf")


async def test_pdf_text_truncated(parse, limits):
    from dataclasses import replace

    data = make_pdf(["\n".join(["가" * 30] * 3), "\n".join(["나" * 30] * 3)], toc=False)
    result = await parse(data, "pdf", replace(limits, max_text_chars=150))
    assert result["truncated"] is True and len(result["text"]) <= 151


# ── CSV ──────────────────────────────────────────────────
async def test_csv_cp949_and_utf8_sig(parse):
    body = "기관명,제목\n한국철도공사,궤도 연구\n\n"
    for data in (body.encode("cp949"), body.encode("utf-8-sig")):
        result = await parse(data, "csv")
        assert result == {
            "header": ["기관명", "제목"],
            "rows": [{"기관명": "한국철도공사", "제목": "궤도 연구"}],
        }


async def test_csv_row_cap(parse, limits):
    from dataclasses import replace

    data = ("a\n" + "x\n" * 20).encode()
    assert await rejected(parse, data, "csv", replace(limits, max_csv_rows=10)) == "TooManyRows"


async def test_csv_huge_field_rejected(parse):
    data = ("a\n" + "x" * 20_000 + "\n").encode()
    assert await rejected(parse, data, "csv") == "Error"  # csv.Error: field larger than limit


# ── hwp (OLE) ────────────────────────────────────────────
def _record(tag: int, payload: bytes, level: int = 0) -> bytes:
    import struct

    return struct.pack("<I", tag | (level << 10) | (len(payload) << 20)) + payload


def _para(text: str) -> bytes:
    from rra.adapters.sources.alio.extract.hwp import TAG_PARA_TEXT

    return _record(TAG_PARA_TEXT, text.encode("utf-16-le"))


def test_hwp_records_and_paragraph_text_skip_controls():
    import struct

    from rra.adapters.sources.alio.extract.hwp import paragraph_text, records, section_lines

    ctrl = struct.pack("<H", 9) + b"\x00" * 14  # 탭 컨트롤: 코드 1 유닛 + 14 바이트
    body = (
        _record(0x10, b"\x01\x02")  # 다른 레코드는 무시
        + _para("제목 줄\r")
        + _record(0x10 + 51, "앞".encode("utf-16-le") + ctrl + "뒤\n둘째".encode("utf-16-le"))
        + _para("\x1e비분리\x1f공백")
    )
    assert [t for t, _, _ in records(body)] == [16, 67, 67, 67]
    assert paragraph_text("가\x00나\x18다".encode("utf-16-le")) == "가나다"
    # BMP 밖 글자(서로게이트 쌍)는 한 글자로, 짝 없는 서로게이트는 버린다 (JSON 직렬화 가능)
    pair = (
        "𠀀".encode("utf-16-le") + "a".encode("utf-16-le") + b"\x00\xd8" + "b".encode("utf-16-le")
    )
    assert paragraph_text(pair) == "𠀀ab"
    import json

    json.dumps(paragraph_text(pair))
    assert section_lines(body) == ["제목 줄", "앞뒤", "둘째", "비분리 공백"]


def test_hwp_extended_size_records_and_broken_tail():
    import struct

    from rra.adapters.sources.alio.extract.hwp import records

    payload = b"x" * 0x1000
    big = struct.pack("<I", 67 | (0xFFF << 20)) + struct.pack("<I", len(payload)) + payload
    [(tag, _, got)] = list(records(big + b"\x01\x02"))  # 꼬리 2바이트는 머리가 안 됨 → 끝
    assert tag == 67 and got == payload
    assert list(records(struct.pack("<I", 67 | (50 << 20)) + b"short")) == []  # 선언 크기 > 실제


def test_hwp_inflate_caps_decompressed_size():
    import zlib

    from rra.adapters.sources.alio.extract.hwp import SectionTooLarge, inflate

    raw = zlib.compress(b"a" * 10_000)[2:-4]  # raw deflate
    assert inflate(raw, 10_000) == b"a" * 10_000
    with pytest.raises(SectionTooLarge):
        inflate(raw, 9_999)


async def test_hwp_garbage_and_non_hwp_ole_rejected(parse):
    assert (
        await rejected(parse, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600, "hwp")
        == "NotHwp"
    )
    assert await rejected(parse, b"not ole at all", "hwp") == "NotHwp"


def _real_hwp():
    root = Path("data/inbox/own_docs")
    for p in sorted(root.rglob("*.hwp")) if root.is_dir() else []:
        if "공시" in unicodedata.normalize("NFC", p.name) and "~$" not in p.name:
            return p
    done = Path("data/inbox/own_docs/_done")
    for p in sorted(done.rglob("*.hwp")) if done.is_dir() else []:
        if "공시" in unicodedata.normalize("NFC", p.name):
            return p
    return None


@pytest.mark.skipif(
    _real_hwp() is None, reason="실물 공시용 요약문(hwp)이 data/inbox/own_docs 에 없음"
)
async def test_real_disclosure_hwp_has_labeled_sections(limits):
    path = _real_hwp()
    fd = os.open(path, os.O_RDONLY)
    try:
        result = await run_parser(fd, "hwp", limits)
    finally:
        os.close(fd)
    text = result["text"]
    assert len(text) > 200 and ("연구목적" in text or "연구내용" in text)
    assert "\x00" not in text and result["truncated"] is False


# ── xlsx / xls ────────────────────────────────────────────
def _xlsx(rows, sheet="과제") -> bytes:
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def test_xlsx_rows_dates_numbers_and_empty_rows(parse):
    import datetime as dt

    data = _xlsx(
        [
            ["제목", None, "시작"],
            [None, None, None],
            ["과제 A", 3, dt.datetime(2024, 5, 1)],
            ["과제 B", 1.5, dt.date(2025, 1, 2)],
        ]
    )
    result = await parse(data, "xlsx")
    [sheet] = result["sheets"]
    assert sheet["name"] == "과제"
    assert sheet["rows"] == [
        ["제목", None, "시작"],
        ["과제 A", "3", "2024-05-01T00:00:00"],
        ["과제 B", "1.5", "2025-01-02T00:00:00"],  # openpyxl 은 날짜도 datetime 으로 준다
    ]


async def test_xlsx_row_cap_and_bomb_guard(parse, limits):
    from dataclasses import replace

    data = _xlsx([["t"]] + [[f"r{i}"] for i in range(20)])
    assert await rejected(parse, data, "xlsx", replace(limits, max_csv_rows=10)) == "TooManyRows"
    assert await rejected(parse, zip_bomb(), "xlsx") in {"ArchiveTooLarge", "InvalidFileException"}
    assert await rejected(parse, b"PK\x03\x04garbage", "xlsx") in {"BadZipFile", "ArchiveTooLarge"}


REAL_XLS = Path("data/inbox/own/연구과제 현황.xls")


@pytest.mark.skipif(not REAL_XLS.exists(), reason="실물 xls 가 data/inbox/own 에 없음")
async def test_real_xls_is_read_with_dates(limits):
    fd = os.open(REAL_XLS, os.O_RDONLY)
    try:
        result = await run_parser(fd, "xls", limits)
    finally:
        os.close(fd)
    [sheet] = result["sheets"]
    header = next(r for r in sheet["rows"] if r and r[0] == "구분")
    assert "연구과제명" in header and any("20" in (c or "") for r in sheet["rows"][4:8] for c in r)


# ── pdf_pages (P2-8 표 사실 — 쪽별 텍스트) ───────────────
async def test_pdf_pages_keeps_page_boundaries(parse):
    data = make_pdf(["첫 쪽\n매출액 5,100", "둘째 쪽"], toc=False)
    result = await parse(data, "pdf_pages")
    assert len(result["pages"]) == 2 and result["truncated"] is False
    assert "매출액 5,100" in result["pages"][0] and "둘째 쪽" in result["pages"][1]


async def test_pdf_pages_encrypted_rejected(parse):
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secret")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
    assert await rejected(parse, data, "pdf_pages") == "EncryptedDocument"
