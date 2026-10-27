"""NTIS 과제 레코드(flatten 된 HIT) → Document(doc_type="rnd_project", raw.kind="national_rnd").

순수 함수.

필드 이름은 공개 매뉴얼 "국가R&D 과제검색 서비스(대국민용)"(2021-02-08) 응답명세 기준
(tests/fixtures/ntis/README.md). overlap.tier_of 에 맞춘다: 주관연구기관명 → orgs
태그(korail·krri·kr). 수행 부서 필드는 응답에 없다 → department 없음 (코레일 철도연구원 과제도 own
이 아니라 national_rnd 티어로 판정된다). 사람 이름(Manager/Name 연구책임자, Researchers/Name
참여연구원)은 읽지 않는다 — authors 는 항상 빈 목록.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from rra.adapters.sources._orgs import org_tags
from rra.domain.models import Document

KIND = "national_rnd"
FIELDS: dict[str, tuple[str, ...]] = {
    "id": ("ProjectNumber",),
    "title": ("ProjectTitle/Korean", "ProjectTitle/English", "ProjectTitle"),
    "goal": ("Goal/Full", "Goal/Teaser", "Goal"),
    "abstract": ("Abstract/Full", "Abstract/Teaser", "Abstract"),
    "effect": ("Effect/Full", "Effect/Teaser", "Effect"),
    "orgs": ("ResearchAgency/Name", "ResearchAgency"),
    "order_agency": ("OrderAgency/Name", "OrderAgency"),
    "start": ("ProjectPeriod/TotalStart", "ProjectPeriod/Start"),
    "end": ("ProjectPeriod/TotalEnd", "ProjectPeriod/End"),
    "ministry": ("Ministry/Name", "Ministry"),
    "budget": ("TotalFunds", "GovernmentFunds"),
    "year": ("ProjectYear",),
    "keywords": ("Keyword/Korean", "Keyword"),
    "phase": ("DevelopmentPhases",),
    "science_class": ("ScienceClass/Medium", "ScienceClass/Large"),
}
MAX_TITLE_CHARS = 500
MAX_TEXT_CHARS = 8000
_ID = re.compile(r"^[0-9A-Za-z_-]{4,40}$")
_DATE = re.compile(r"(\d{4})[-./]?(\d{1,2})[-./]?(\d{1,2})")
_HIGHLIGHT = re.compile(r"</?span[^>]*>|&lt;/?span[^&]*&gt;")


def strip_highlight(text: str) -> str:
    """검색어 강조 태그(`<span class="search_word">`, 이스케이프된 꼴 포함) 제거."""
    return " ".join(_HIGHLIGHT.sub("", text).split())


def pick(raw: Mapping[str, Any], names: tuple[str, ...]) -> str:
    for name in names:
        value = raw.get(name)
        if isinstance(value, str) and value.strip():
            return strip_highlight(value)
    return ""


def _pick(raw: Mapping[str, Any], field: str) -> str:
    return pick(raw, FIELDS[field])


def parse_date(value: str) -> date | None:
    m = _DATE.search(value)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def split_list(value: str) -> list[str]:
    return [v.strip() for v in re.split(r"\s*[|,;]\s*", value) if v.strip()]


def normalize_project(
    raw: Mapping[str, Any], institutions: Sequence[Mapping[str, Any]]
) -> Document:
    native = _pick(raw, "id")
    if not _ID.match(native):
        raise ValueError("NTIS 과제고유번호가 없거나 형식이 다릅니다.")
    title = _pick(raw, "title")[:MAX_TITLE_CHARS]
    if not title:
        raise ValueError(f"ntis:{native} 과제명 없음")
    parts = [
        (label, _pick(raw, key))
        for label, key in (("연구목표", "goal"), ("연구내용", "abstract"), ("기대효과", "effect"))
    ]
    summary = "\n\n".join(f"[{label}] {text}" for label, text in parts if text)[:MAX_TEXT_CHARS]
    start, end = parse_date(_pick(raw, "start")), parse_date(_pick(raw, "end"))
    org_names = [n for n in re.split(r"\s*\|\s*", _pick(raw, "orgs")) if n]
    year = _pick(raw, "year")
    return Document(
        doc_id=f"ntis:{native}",
        source="ntis",
        doc_type="rnd_project",
        title=title,
        abstract=summary or None,
        pub_date=start or (date(int(year), 1, 1) if year.isdigit() and len(year) == 4 else None),
        orgs=org_tags(org_names, institutions),
        authors=[],  # 연구책임자·참여연구원 이름은 저장하지 않는다
        lang="ko",
        text_basis="abstract",
        visibility="public",
        project_period=(start, end) if start and end and start <= end else None,
        codes=split_list(_pick(raw, "keywords"))[:20],
        raw={
            "kind": KIND,
            "project_no": native,
            "agencies": org_names[:10],
            "order_agency": _pick(raw, "order_agency") or None,
            "ministry": _pick(raw, "ministry") or None,
            "budget": _pick(raw, "budget") or None,
            "year": year or None,
            "phase": _pick(raw, "phase") or None,
            "science_class": _pick(raw, "science_class") or None,
        },
    )
