"""KIPRIS 특허 레코드(flatten 된 dict) → Document(source kipris_kr, doc_type patent). 순수 함수.

freeSearchInfo 응답의 PatentUtilityInfo 요소 태그(공개 구현 기준 후보): ApplicationNumber,
InventionName, Abstract, Applicant, ApplicationDate, OpeningDate, PublicDate, RegistrationNumber,
RegistrationStatus, InternationalpatentclassificationNumber. 실응답 fixture 로 확정한다.

사람 이름은 저장하지 않는다: 발명자 필드는 읽지 않고, 출원인은 기관으로 보이는 이름(회사·공사·
연구원·대학교·법인·공단·재단·㈜ 등)만 남긴다. 개인 출원인은 raw.applicant_kind="person" 으로만 표시.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from rra.adapters.sources._orgs import is_organization, org_tags
from rra.domain.models import Document

FIELDS: dict[str, tuple[str, ...]] = {
    "application_no": ("ApplicationNumber", "applicationNumber", "출원번호"),
    "title": ("InventionName", "inventionTitle", "발명의명칭"),
    "abstract": ("Abstract", "astrtCont", "초록"),
    "applicant": ("Applicant", "applicantName", "출원인"),
    "application_date": ("ApplicationDate", "applicationDate", "출원일자"),
    "opening_date": ("OpeningDate", "openDate", "공개일자"),
    "public_date": ("PublicDate", "publicationDate", "공고일자"),
    "registration_no": ("RegistrationNumber", "registerNumber", "등록번호"),
    "status": ("RegistrationStatus", "registerStatus", "등록상태"),
    "ipc": ("InternationalpatentclassificationNumber", "ipcNumber", "IPC"),
    "public_no": ("PublicNumber", "publicationNumber", "공고번호"),
    "opening_no": ("OpeningNumber", "openNumber", "공개번호"),
}
MAX_TITLE_CHARS = 500
MAX_ABSTRACT_CHARS = 8000
MAX_APPLICANTS = 5
_APP_NO = re.compile(r"^[0-9]{8,16}$")
_DATE = re.compile(r"(\d{4})[-./]?(\d{2})[-./]?(\d{2})")


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


def split_names(value: str) -> list[str]:
    return [n.strip() for n in re.split(r"\s*[|;]\s*", value) if n.strip()]


def normalize_patent(raw: Mapping[str, Any], institutions: Sequence[Mapping[str, Any]]) -> Document:
    native = re.sub(r"[^0-9]", "", _pick(raw, "application_no"))
    if not _APP_NO.match(native):
        raise ValueError("KIPRIS 출원번호가 없거나 형식이 다릅니다.")
    title = _pick(raw, "title")[:MAX_TITLE_CHARS]
    if not title:
        raise ValueError(f"kipris_kr:{native} 발명의 명칭 없음")
    applicants = split_names(_pick(raw, "applicant"))
    orgs_named = [a for a in applicants if is_organization(a)][:MAX_APPLICANTS]
    applied = _date(_pick(raw, "application_date"))
    opened = _date(_pick(raw, "opening_date")) or _date(_pick(raw, "public_date"))
    codes = [c for c in re.split(r"\s*[|,;]\s*", _pick(raw, "ipc")) if c][:20]
    return Document(
        doc_id=f"kipris_kr:{native}",
        source="kipris_kr",
        doc_type="patent",
        title=title,
        abstract=_pick(raw, "abstract")[:MAX_ABSTRACT_CHARS] or None,
        pub_date=opened or applied,
        orgs=org_tags(orgs_named, institutions),
        codes=codes,
        lang="ko",
        application_no=native,
        text_basis="abstract",
        raw={
            "application_no": native,
            "application_date": applied.isoformat() if applied else None,
            "opening_date": opened.isoformat() if opened else None,
            "registration_no": re.sub(r"[^0-9]", "", _pick(raw, "registration_no")) or None,
            "status": _pick(raw, "status")[:40] or None,
            "applicants": orgs_named,  # 기관만. 개인 출원인·발명자 이름은 저장하지 않는다
            "applicant_kind": "organization" if orgs_named else ("person" if applicants else None),
        },
    )
