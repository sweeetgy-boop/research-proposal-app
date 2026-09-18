"""알리오 테스트용 샘플 생성기. 악성 샘플은 저장소에 커밋하지 않고 tmp_path 에 매번 만든다."""

from __future__ import annotations

import io
import zipfile

import pytest

from rra.adapters.sources._sandbox import SandboxLimits

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
SECTION_XML = (
    f'<?xml version="1.0" encoding="UTF-8"?><hs:sec xmlns:hs="x" xmlns:hp="{HP}">'
    "<hp:p><hp:run><hp:t>제1장 서론</hp:t></hp:run></hp:p>"
    "<hp:p><hp:run><hp:t>궤도 틀림<hp:tab/>자동 감지</hp:t></hp:run></hp:p>"
    "<hp:p><hp:run><hp:tbl><hp:tr><hp:tc><hp:subList>"
    "<hp:p><hp:run><hp:t>표 안 문단</hp:t></hp:run></hp:p>"
    "</hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>"
    "<hp:p><hp:run><hp:t>제2장 방법</hp:t></hp:run></hp:p>"
    "</hs:sec>"
)


def make_hwpx(
    sections: dict[str, str | bytes] | None = None,
    *,
    mimetype: bytes = b"application/hwp+zip",
    extra: dict[str, bytes] | None = None,
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), mimetype)  # 무압축 첫 엔트리 (OWPML 관례)
        for name, body in (sections or {"Contents/section0.xml": SECTION_XML}).items():
            zf.writestr(name, body)
        for name, body in (extra or {}).items():
            zf.writestr(name, body)
    return buf.getvalue()


def make_pdf(pages: list[str], *, title: str | None = None, toc: bool = True) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    for text in pages:
        doc.new_page().insert_text((72, 72), text, fontname="korea")
    if title:
        doc.set_metadata({"title": title})
    if toc:
        doc.set_toc([[1, text.splitlines()[0], i + 1] for i, text in enumerate(pages)])
    data = doc.tobytes()
    doc.close()
    return data


def zip_bomb() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), b"application/hwp+zip")
        # 압축비 ~1000:1, 선언 크기는 상한 이내 → 압축비 검사로 걸러져야 한다
        zf.writestr("Contents/section0.xml", b"\x00" * (2 * 1024 * 1024))
    return buf.getvalue()


BILLION_LAUGHS = (
    '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
    '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>'
    f'<hs:sec xmlns:hs="x" xmlns:hp="{HP}"><hp:p><hp:t>&lol2;</hp:t></hp:p></hs:sec>'
)
XXE = (
    '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
    f'<hs:sec xmlns:hs="x" xmlns:hp="{HP}"><hp:p><hp:t>&x;</hp:t></hp:p></hs:sec>'
)


@pytest.fixture
def limits():
    return SandboxLimits(timeout_sec=30, mem_mb=1024, max_input_mb=5, max_pdf_pages=50)
