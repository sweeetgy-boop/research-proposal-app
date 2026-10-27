"""ScienceON 레코드(flatten 된 dict) → Document. 순수 함수.

metaCode 는 2026-10-27 실응답 fixture(tests/fixtures/scienceon/)로 확정했다.
- ARTI(국내논문): CN·DBCode·Title·Title2·Abstract·Abstract2·Author·Author2·Affiliation·Affiliation2·
  Publisher·JournalName·Pubyear·Pubdate·DOI(https://doi.org/… 형태)·ContentURL·FulltextURL·Keyword·
  Lang·Country
- REPORT(국내연구보고서): CN·Title·Abstract·Author·Contributors·Publisher·ManagingAgency·
  ResearchMngAgency·CoResearchOrg·CollaboratingOrg·Pubyear·Pubdate(월·일이 00 일 수 있음)·
  ContentURL·FulltextURL·Keyword·Pjn
- PATENT(특허): CN·DBCode·Title·Abstract·Applicants·ApplNum·ApplDate·PublDate·GrantDate·IPC·
  PatentStatus·Nation·NationCode·ContentURL (발명자 항목은 출력에 없다)

사람 이름은 저장하지 않는다 (KIPRIS 와 같은 규칙): Author·Author2·Contributors 는 읽지 않고,
출원인은 기관으로 보이는 이름만 남긴다. 기관명(Affiliation·Publisher·수행·관리기관·출원인)은
raw.orgs_named 에, 기관 태그(korail·krri·kr)는 orgs 에 둔다.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from rra.adapters.sources._orgs import is_organization, org_tags
from rra.domain.models import Document

FIELDS: dict[str, tuple[str, ...]] = {
    "id": ("CN",),
    "title": ("Title", "Title2"),
    "abstract": ("Abstract", "Abstract2"),
    "year": ("Pubdate", "Pubyear", "ApplDate", "PublDate"),
    "doi": ("DOI",),
    "url": ("ContentURL", "FulltextURL"),
    "lang": ("Lang", "Nation"),
    "keyword": ("Keyword",),
    "dbcode": ("DBCode",),
    # 기관(사람 이름 아님). 순서대로 모두 모은다.
    "orgs": (
        "Affiliation",
        "Publisher",
        "CoResearchOrg",
        "CollaboratingOrg",
        "ManagingAgency",
        "ResearchMngAgency",
    ),
    "applicants": ("Applicants",),
    "application_no": ("ApplNum",),
    "ipc": ("IPC",),
    "status": ("PatentStatus",),
    "project_no": ("Pjn",),
}
PERSON_FIELDS = ("Author", "Author2", "Contributors")  # 읽지 않는다
DOC_TYPES = {"ARTI": "paper", "REPORT": "internal_report", "PATENT": "patent"}
MAX_TITLE_CHARS = 500
MAX_ABSTRACT_CHARS = 8000
MAX_ORGS = 10
_ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_TAG = re.compile(r"<[^>]{0,200}>")
_DOI = re.compile(r"10\.\d{4,9}/\S+")
_DATE = re.compile(r"^(\d{4})(\d{2})?(\d{2})?")
_SPLIT = re.compile(r"\s*[;|,]\s*")
_URL = re.compile(r"^https?://[A-Za-z0-9.-]+(?::\d+)?/[^\s<>\"']*$")


def _pick(raw: Mapping[str, Any], field: str) -> str:
    for name in FIELDS[field]:
        value = raw.get(name)
        if isinstance(value, str) and value.strip():
            return _TAG.sub("", value).strip()
    return ""


def _pick_all(raw: Mapping[str, Any], field: str) -> list[str]:
    names: list[str] = []
    for name in FIELDS[field]:
        value = raw.get(name)
        if isinstance(value, str):
            names.extend(n for n in _SPLIT.split(_TAG.sub("", value)) if n.strip())
    return names


def _date(value: str) -> date | None:
    """YYYYMMDD → date. 월·일이 00 이거나 없으면 1월·1일로 내린다 (REPORT Pubdate '20190400')."""
    m = _DATE.match(value)
    if not m:
        return None
    year = int(m.group(1))
    month = int(m.group(2) or 0) or 1
    day = int(m.group(3) or 0) or 1
    try:
        return date(year, month, day)
    except ValueError:
        return date(year, 1, 1)


def _lang(value: str) -> str:
    v = value.strip().lower()
    if v.startswith("한국어") or v in {"ko", "kr", "kor"}:
        return "ko"
    if v.startswith("영어") or v in {"en", "eng"}:
        return "en"
    return "ko"


def normalize_record(
    raw: Mapping[str, Any], institutions: Sequence[Mapping[str, Any]] = ()
) -> Document:
    native = _pick(raw, "id")
    if not _ID.match(native):
        raise ValueError("ScienceON 레코드 id(CN) 가 없거나 형식이 다릅니다.")
    title = _pick(raw, "title")[:MAX_TITLE_CHARS]
    if not title:
        raise ValueError(f"scienceon:{native} 제목 없음")
    target = str(raw.get("target") or "")
    doc_type = DOC_TYPES.get(target, "paper")
    doi_match = _DOI.search(_pick(raw, "doi"))
    url = _pick(raw, "url")
    applicants = _pick_all(raw, "applicants")
    orgs_named = [n for n in [*_pick_all(raw, "orgs"), *applicants] if is_organization(n)]
    orgs_named = list(dict.fromkeys(n[:200] for n in orgs_named))[:MAX_ORGS]
    codes: list[str] = []
    if doc_type == "patent":
        codes = [c for c in _SPLIT.split(_pick(raw, "ipc")) if c][:20]
    app_no = re.sub(r"[^0-9]", "", _pick(raw, "application_no")) if doc_type == "patent" else ""
    return Document(
        doc_id=f"scienceon:{native}",
        source="scienceon",
        doc_type=doc_type,  # type: ignore[arg-type]
        title=title,
        abstract=_pick(raw, "abstract")[:MAX_ABSTRACT_CHARS] or None,
        pub_date=_date(_pick(raw, "year")),
        orgs=org_tags(orgs_named, institutions),
        authors=[],  # 사람 이름은 저장하지 않는다
        codes=codes,
        lang=_lang(_pick(raw, "lang")),
        text_basis="abstract",
        url=url if _URL.match(url) else None,
        doi=doi_match.group(0).rstrip(".").lower() if doi_match else None,
        application_no=app_no or None,
        raw={
            "cn": native,
            "target": target,
            "dbcode": _pick(raw, "dbcode") or None,
            "orgs_named": orgs_named,
            "applicant_kind": (
                "organization"
                if any(is_organization(a) for a in applicants)
                else ("person" if applicants else None)
            ),
            "status": _pick(raw, "status") or None,
            "project_no": _pick(raw, "project_no") or None,
            "keywords": [k for k in re.split(r"\s*[.;,]\s*", _pick(raw, "keyword")) if k][:20],
        },
    )
