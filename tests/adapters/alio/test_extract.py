"""PDF·HWPX·CSV 추출 — 항상 샌드박스를 거쳐 실행 (악성 샘플이 본체에서 파싱되지 않음)."""

import os

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
