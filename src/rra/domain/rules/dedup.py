"""8. 교차 소스 중복 제거. 순수 함수."""

from __future__ import annotations

import re

from rra.domain.models import Document

# 같은 문서면 원문 > 공개 요약 > 초록 순으로 남긴다
BASIS_RANK = {"full_text": 2, "summary": 1, "abstract": 0}


def _better(new: Document, old: Document) -> bool:
    rn, ro = BASIS_RANK[new.text_basis], BASIS_RANK[old.text_basis]
    if rn != ro:
        return rn > ro
    if len(new.body or "") != len(old.body or ""):
        return len(new.body or "") > len(old.body or "")  # 같은 근거면 본문이 긴 쪽
    return len(new.abstract or "") > len(old.abstract or "")  # 본문도 같으면 초록이 긴 쪽


def should_replace(existing: Document | None, new: Document) -> bool:
    """저장된 문서를 new 로 덮어써도 되는가. 근거 수준이 내려가면(원문 → 요약) 안 된다."""
    return existing is None or BASIS_RANK[new.text_basis] >= BASIS_RANK[existing.text_basis]


def _norm_title(t: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", t.lower())


REPORT_TYPES = frozenset({"report", "internal_report"})


def report_identity(d: Document) -> str | None:
    """보고서의 교차 자료원 동일성 키 — 과제번호 + 제목(정규화).

    같은 과제의 연차 보고서는 제목이 달라 합치지 않고, 같은 보고서가 NTIS(doc_type report)와
    ScienceON(internal_report, raw.project_no=Pjn)에 모두 있으면 하나로 본다.
    과제번호가 없으면 None (제목 키로 넘어간다)."""
    if d.doc_type not in REPORT_TYPES:
        return None
    project_no = d.raw.get("project_no")
    if not isinstance(project_no, str) or not project_no.strip():
        return None
    return f"report:{re.sub(r'[^0-9A-Za-z]', '', project_no).lower()}:{_norm_title(d.title)}"


def same_report(a: Document, b: Document) -> bool:
    """두 보고서가 같은 것인가 (과제번호·제목 일치, 발행연도가 둘 다 있으면 그것도 같아야 한다)."""
    ka, kb = report_identity(a), report_identity(b)
    if ka is None or ka != kb:
        return False
    ya, yb = (a.pub_date.year if a.pub_date else None), (b.pub_date.year if b.pub_date else None)
    return ya is None or yb is None or ya == yb


def identity_key(d: Document) -> str:
    if d.doc_type == "rnd_project":
        # 과제는 고유번호(doc_id)로 식별 — 같은 제목의 보고서·논문과 합쳐지지 않게
        return f"project:{d.doc_id}"
    report = report_identity(d)
    if report:
        year = d.pub_date.year if d.pub_date else ""
        return f"{report}:{year}"
    if d.doi:
        return f"doi:{d.doi.lower()}"
    if d.application_no:
        return f"app:{re.sub(r'[^0-9A-Za-z]', '', d.application_no)}"
    return f"title:{_norm_title(d.title)}"


def dedup(docs: list[Document]) -> list[Document]:
    seen: dict[str, Document] = {}
    for d in docs:
        k = identity_key(d)
        if k not in seen or _better(d, seen[k]):
            seen[k] = d
    return list(seen.values())
