"""ScienceON 레코드(flatten 된 dict) → Document. 순수 함수.

metaCode 이름은 가이드 예시(CN·Title·Author·Pubyear…)를 바탕으로 한 **후보 목록**이다.
실응답 fixture(tests/fixtures/scienceon/)로 확정한 뒤 후보를 줄인다.
그 전에는 정규화 테스트가 skip 된다.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from rra.domain.models import Document

FIELDS: dict[str, tuple[str, ...]] = {
    "id": ("CN", "ControlNumber"),
    "title": ("Title", "TI", "ArticleTitle"),
    "abstract": ("Abstract", "AB"),
    "authors": ("Author", "AU"),
    "year": ("Pubyear", "PublicationYear", "PY"),
    "doi": ("DOI",),
    "url": ("ContentURL", "FulltextURL", "URL"),
    "orgs": ("Affiliation", "Publisher"),
}
DOC_TYPES = {"ARTI": "paper", "REPORT": "internal_report"}
MAX_TITLE_CHARS = 500
_ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_TAG = re.compile(r"<[^>]{0,200}>")
_DOI = re.compile(r"10\.\d{4,9}/\S+")


def _pick(raw: dict[str, Any], field: str) -> str:
    for name in FIELDS[field]:
        value = raw.get(name)
        if isinstance(value, str) and value.strip():
            return _TAG.sub("", value).strip()
    return ""


def _year(value: str) -> date | None:
    m = re.match(r"^(\d{4})", value)
    return date(int(m.group(1)), 1, 1) if m else None


def normalize_record(raw: dict[str, Any]) -> Document:
    native = _pick(raw, "id")
    if not _ID.match(native):
        raise ValueError("ScienceON 레코드 id(CN) 가 없거나 형식이 다릅니다.")
    title = _pick(raw, "title")[:MAX_TITLE_CHARS]
    if not title:
        raise ValueError(f"scienceon:{native} 제목 없음")
    doi_match = _DOI.search(_pick(raw, "doi"))
    url = _pick(raw, "url")
    authors = [a.strip() for a in re.split(r"[;|]", _pick(raw, "authors")) if a.strip()]
    return Document(
        doc_id=f"scienceon:{native}",
        source="scienceon",
        doc_type=DOC_TYPES.get(str(raw.get("target")), "paper"),
        title=title,
        abstract=_pick(raw, "abstract") or None,
        pub_date=_year(_pick(raw, "year")),
        authors=authors[:50],
        lang="ko",
        text_basis="abstract",
        url=url if url.startswith("https://") else None,
        doi=doi_match.group(0).rstrip(".").lower() if doi_match else None,
        raw={"cn": native, "target": raw.get("target")},
    )
