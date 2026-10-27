"""판독 결과 → 적재용 Document/Chunk (P3 ⑥ 적재 준비, 코드만).

- 이미지 하나가 문서 하나(`<source>:img:<sha256 앞 16자>`)가 된다. text_basis="image_vision",
  source 는 이미지가 실린 페이지 문서를 따른다(없으면 manifest 의 source, 기본 korail_web).
  그 source 가 아직 SourceType 에 없으면(크롤 레인이 추가하기 전) unknown_source 로 건너뛴다.
- 본문이 이기는 규칙: 페이지 본문에 이미 있는 줄은 이미지 텍스트에서 뺀다. 남는 줄이 없으면 그
이미지는
  적재하지 않는다 (페이지 본문이 같은 내용을 더 믿을 만하게 담고 있다).
- 실패한 Argon(status=failed)·상한 초과(ocr_only) 는 OCR 텍스트만 적재한다. OCR 도 없으면 건너뛴다.
- 미확인 수치가 든 문장에는 "[판독 확인 필요]" 표식을 붙인다 (vision_trust.mark_unconfirmed).
- 개인정보(전화·이메일·이름)는 domain/rules/privacy 로 지운다.
- raw.image 에 화면용 메타데이터: url(원본 이미지)·page_url·page_doc_id·sha256·image_type·status·
  unconfirmed_numbers·confirmed_numbers. 화면은 basis=image_vision 이면 "이미지 판독" 배지 + 원본
  링크.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from rra.domain.models import Chunk, Document
from rra.domain.models.vision import ImageReadResult, VisionReading
from rra.domain.rules.privacy import strip_personal
from rra.domain.rules.vision_trust import mark_unconfirmed
from rra.domain.services.chunking import chunk_document

DOC_ID_HASH_CHARS = 16
MAX_TITLE_CHARS = 200
_WS = re.compile(r"\s+")


@dataclass
class LinkReport:
    documents: list[Document] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)  # sha256 → 이유
    removed_personal: dict[str, int] = field(default_factory=dict)


def _norm(line: str) -> str:
    return _WS.sub("", line).lower()


def structure_lines(reading: VisionReading) -> list[str]:
    """structure 를 사람이 읽는 줄로. 표는 행마다 "a | b", 체계도는 "비전: …" 식."""
    s = reading.structure
    out: list[str] = []
    if not s:
        return out
    if reading.image_type == "표":
        cols = (
            [str(c) for c in s.get("cols", []) if str(c).strip()]
            if isinstance(s.get("cols"), list)
            else []
        )
        if cols:
            out.append(" | ".join(cols))
        rows = s.get("rows") if isinstance(s.get("rows"), list) else []
        for row in rows:
            if isinstance(row, list):
                out.append(" | ".join(str(c) for c in row))
            elif isinstance(row, dict):
                out.append(" | ".join(f"{k}: {v}" for k, v in row.items()))
            elif isinstance(row, str):
                out.append(row)
        if s.get("units"):
            out.append(f"단위: {s['units']}")
        return out
    for key, value in s.items():
        if isinstance(value, list):
            items = [
                str(v) if not isinstance(v, dict) else ", ".join(f"{k}: {x}" for k, x in v.items())
                for v in value
            ]
            out.append(f"{key}: " + " / ".join(i for i in items if i))
        elif isinstance(value, dict):
            out.append(f"{key}: " + ", ".join(f"{k}: {v}" for k, v in value.items()))
        elif value not in (None, ""):
            out.append(f"{key}: {value}")
    return out


def compose_text(result: ImageReadResult) -> str:
    """판독 본문: Argon text(+structure) 우선, 없으면 OCR 줄. 둘 다 없으면 빈 문자열."""
    reading = result.reading
    lines: list[str] = []
    if reading is not None:
        if reading.text:
            lines.extend(ln for ln in reading.text.splitlines() if ln.strip())
        lines.extend(structure_lines(reading))
        if reading.summary and reading.summary.strip() not in {ln.strip() for ln in lines}:
            lines.append(reading.summary)
    elif result.ocr is not None:
        lines.extend(ln.text for ln in result.ocr.lines if ln.text.strip())
    return "\n".join(lines)


def drop_body_overlap(text: str, body: str | None) -> str:
    """페이지 본문에 이미 있는 줄을 뺀다 (공백·대소문자 무시)."""
    if not body:
        return text
    body_norm = _norm(body)
    kept = [ln for ln in text.splitlines() if ln.strip() and _norm(ln) not in body_norm]
    return "\n".join(kept)


def link_readings(
    results: Iterable[ImageReadResult],
    pages: Mapping[str, Document] | None = None,
    *,
    chunk_max_chars: int = 1500,
    default_source: str = "korail_web",
) -> LinkReport:
    """pages: page_url 또는 page_doc_id → 페이지 Document (본문 비교·source 결정용)."""
    pages = pages or {}
    report = LinkReport()
    for r in results:
        page = pages.get(r.item.page_doc_id or "") or pages.get(r.item.page_url or "")
        text = compose_text(r)
        if not text.strip():
            report.skipped[r.sha256] = "no_text"
            continue
        text = drop_body_overlap(text, page.body if page else None)
        if not text.strip():
            report.skipped[r.sha256] = "body_wins"
            continue
        text = mark_unconfirmed(text, r.unconfirmed_numbers)
        cleaned = strip_personal(text)
        for k, n in cleaned.removed.items():
            report.removed_personal[k] = report.removed_personal.get(k, 0) + n
        title = _title(r, page)
        source = page.source if page else (r.item.source or default_source)
        try:
            doc = Document(
                doc_id=f"{source}:img:{r.sha256[:DOC_ID_HASH_CHARS]}",
                source=source,  # type: ignore[arg-type]
                doc_type="web_page",
                title=strip_personal(title).text,
                body=cleaned.text,
                url=r.item.page_url or r.item.url,
                orgs=list(page.orgs) if page else ["korail"],
                department=page.department if page else None,
                lang="ko",
                text_basis="image_vision",
                visibility=page.visibility if page else "public",
                valid_until=page.valid_until if page else None,
                raw={"image": _image_meta(r, page)},
            )
        except ValidationError:  # source 가 SourceType 에 없다 (크롤 레인의 source 추가 전)
            report.skipped[r.sha256] = "unknown_source"
            continue
        chunks = [
            c.model_copy(update={"basis": "image_vision", "visibility": doc.visibility})
            for c in chunk_document(doc, max_chars=chunk_max_chars)
        ]
        report.documents.append(doc)
        report.chunks.extend(chunks)
    return report


def _title(r: ImageReadResult, page: Document | None) -> str:
    reading_title = r.reading.title.strip() if r.reading and r.reading.title else ""
    base = reading_title or (r.item.alt or "").strip() or (r.item.caption or "").strip()
    page_title = (page.title if page else r.item.page_title) or ""
    if base and page_title and base != page_title:
        title = f"{page_title} — {base}"
    else:
        title = base or page_title or "이미지"
    if not reading_title and not r.item.alt and not r.item.caption:
        title = f"{title} (이미지)"
    return title[:MAX_TITLE_CHARS]


def _image_meta(r: ImageReadResult, page: Document | None) -> dict[str, Any]:
    return {
        "sha256": r.sha256,
        "url": r.item.url,
        "path": r.item.path,
        "page_url": r.item.page_url,
        "page_doc_id": page.doc_id if page else r.item.page_doc_id,
        "image_type": r.reading.image_type if r.reading else None,
        "status": r.status,
        "ocr": r.ocr is not None,
        "uncertain": bool(r.reading and r.reading.uncertain),
        "confirmed_numbers": list(r.confirmed_numbers),
        "unconfirmed_numbers": list(r.unconfirmed_numbers),
        "width": r.item.width,
        "height": r.item.height,
    }
