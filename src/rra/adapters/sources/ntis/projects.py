"""NTIS 과제 레코드(flatten 된 dict) → Document(doc_type="rnd_project"). 순수 함수.

overlap.tier_of 에 맞춘다: 수행·주관기관명 → orgs 태그(korail·krri·kr), 수행 부서 → department
("철도연구원" 이면 own 티어). 필드 이름은 후보 목록 — 실응답 fixture 로 확정한다.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from rra.adapters.sources._orgs import org_tags
from rra.domain.models import Document

FIELDS: dict[str, tuple[str, ...]] = {
    "id": ("ProjectNumber", "PjtNo", "과제고유번호", "PROJECT_NUMBER"),
    "title": ("ProjectTitle/Korean", "ProjectTitle", "PjtNm", "과제명"),
    "goal": ("Goal/Teaser", "Goal", "연구목표"),
    "abstract": ("Abstract/Teaser", "Abstract", "연구내용", "요약"),
    "effect": ("Effect/Teaser", "Effect", "기대효과"),
    "orgs": ("ResearchAgency/Name", "ResearchAgency", "LeadAgency", "수행기관", "주관기관"),
    "department": ("ResearchAgencyDepartment", "Department", "수행부서"),
    "manager": ("Manager/Name", "Manager", "연구책임자"),
    "start": ("ProjectPeriod/Start", "TotalPeriod/Start", "연구시작일"),
    "end": ("ProjectPeriod/End", "TotalPeriod/End", "연구종료일"),
    "ministry": ("Ministry/Name", "Ministry", "부처명"),
    "budget": ("TotalFunds", "GovernmentFunds", "연구비"),
    "year": ("ProjectYear", "기준년도"),
    "keywords": ("Keyword/Korean", "Keyword", "키워드"),
}
MAX_TITLE_CHARS = 500
MAX_TEXT_CHARS = 8000
_ID = re.compile(r"^[0-9A-Za-z_-]{4,40}$")
_DATE = re.compile(r"(\d{4})[-./]?(\d{1,2})[-./]?(\d{1,2})")


def _pick(raw: Mapping[str, Any], field: str) -> str:
    for name in FIELDS[field]:
        value = raw.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _date(value: str) -> date | None:
    m = _DATE.search(value)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


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
    start, end = _date(_pick(raw, "start")), _date(_pick(raw, "end"))
    org_names = [n for n in re.split(r"\s*\|\s*", _pick(raw, "orgs")) if n]
    department = _pick(raw, "department")
    return Document(
        doc_id=f"ntis:{native}",
        source="ntis",
        doc_type="rnd_project",
        title=title,
        abstract=summary or None,
        pub_date=start,
        orgs=org_tags([*org_names, department], institutions),
        authors=[m for m in re.split(r"\s*\|\s*", _pick(raw, "manager")) if m][:10],
        lang="ko",
        department=department or None,
        project_period=(start, end) if start and end and start <= end else None,
        codes=[k for k in re.split(r"\s*[|,;]\s*", _pick(raw, "keywords")) if k][:20],
        raw={
            "project_no": native,
            "agencies": org_names[:10],
            "ministry": _pick(raw, "ministry") or None,
            "budget": _pick(raw, "budget") or None,
            "year": _pick(raw, "year") or None,
        },
    )
