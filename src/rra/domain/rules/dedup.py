"""8. 교차 소스 중복 제거. 순수 함수."""

from __future__ import annotations

import re

from rra.domain.models import Document


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
        if k not in seen:
            seen[k] = d
        else:
            # 본문이 더 긴 쪽을 유지
            if len(d.body or "") > len(seen[k].body or ""):
                seen[k] = d
    return list(seen.values())
