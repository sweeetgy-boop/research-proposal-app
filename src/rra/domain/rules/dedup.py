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
    return len(new.body or "") > len(old.body or "")  # 같은 근거면 본문이 긴 쪽


def should_replace(existing: Document | None, new: Document) -> bool:
    """저장된 문서를 new 로 덮어써도 되는가. 근거 수준이 내려가면(원문 → 요약) 안 된다."""
    return existing is None or BASIS_RANK[new.text_basis] >= BASIS_RANK[existing.text_basis]


def _norm_title(t: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", t.lower())


def identity_key(d: Document) -> str:
    if d.doc_type == "rnd_project":
        # 과제는 고유번호(doc_id)로 식별 — 같은 제목의 보고서·논문과 합쳐지지 않게
        return f"project:{d.doc_id}"
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
