"""PDF 텍스트·목차 추출. 샌드박스 자식 프로세스에서만 import 된다.

페이지 수 상한, 암호 문서 거부. 자바스크립트·첨부·링크·폼은 건드리지 않는다(텍스트 추출만).
"""

from __future__ import annotations

from typing import Any

MAX_TOC = 500
MAX_HEADING_CHARS = 200


class EncryptedDocument(ValueError):
    pass


class TooManyPages(ValueError):
    pass


def extract(data: bytes, limits: dict[str, Any]) -> dict[str, Any]:
    import pymupdf

    pymupdf.TOOLS.mupdf_display_errors(False)
    max_chars = int(limits["max_text_chars"])
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        if doc.needs_pass:
            raise EncryptedDocument("encrypted")
        pages = doc.page_count
        if pages > int(limits["max_pdf_pages"]):
            raise TooManyPages("pages")
        parts: list[str] = []
        total = 0
        truncated = False
        for page in doc:
            text = page.get_text("text")
            if total + len(text) > max_chars:
                parts.append(text[: max_chars - total])
                truncated = True
                break
            parts.append(text)
            total += len(text)
        toc = [
            str(title)[:MAX_HEADING_CHARS]
            for _level, title, *_ in doc.get_toc(simple=True)[:MAX_TOC]
            if str(title).strip()
        ]
        meta_title = (doc.metadata or {}).get("title") or None
    return {
        "text": "\n".join(parts),
        "toc": toc,
        "pages": pages,
        "meta_title": meta_title[:MAX_HEADING_CHARS] if meta_title else None,
        "truncated": truncated,
    }
