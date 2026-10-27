"""Q4 채택 과제 본보기 — 공개 자료(공시용 요약문·사내 과제 기록) 중 완료·수행 과제에서 섹션별
본보기 문장.

구성·문체 참고용이다. 프롬프트에 "내용 인용 금지" 로 들어가고, 본보기 doc_id 를 evidence 로 쓴
문장은 검증 규칙(forbidden ids)으로 막는다. 골든셋 정답 과제 자신은 제외한다([4]).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from rra.domain.models import Document
from rra.domain.rules.llm_output import clean_sentence

ELIGIBLE_STATUS = frozenset({"completed", "ongoing"})
# 공시용 요약문의 항목 머리 → 양식 섹션 키
HEADINGS: dict[str, str] = {
    "연구목적": "objective",
    "연구 목적": "objective",
    "연구내용": "method",
    "연구 내용": "method",
    "연구방법": "method",
    "기대효과": "expected_management",
    "기대 효과": "expected_management",
    "활용계획": "utilization",
    "활용 계획": "utilization",
}
_HEAD = re.compile(r"(?m)^\s*(연구 ?목적|연구 ?내용|연구 ?방법|기대 ?효과|활용 ?계획)\s*[:：]\s*")
_SPLIT = re.compile(r"(?<=[.。])\s+|\n+")


def eligible(doc: Document) -> bool:
    status = str((doc.raw or {}).get("status") or "")
    public = doc.visibility != "internal"
    return public and (status in ELIGIBLE_STATUS or doc.text_basis == "summary")


def section_sentences(doc: Document, *, per_section: int = 2) -> dict[str, list[str]]:
    """요약문을 항목 머리로 나눠 섹션별 문장 1~2개."""
    text = "\n".join(p for p in (doc.abstract, doc.body) if p)  # 제목은 항목 머리가 아니다
    out: dict[str, list[str]] = {}
    parts = _HEAD.split(text)
    # parts = [앞, 머리1, 본문1, 머리2, 본문2, …]
    for i in range(1, len(parts) - 1, 2):
        key = HEADINGS.get(parts[i].replace(" ", ""), HEADINGS.get(parts[i]))
        if key is None:
            continue
        sentences = [clean_sentence(s) for s in _SPLIT.split(parts[i + 1]) if clean_sentence(s)]
        sentences = [s for s in sentences if 8 <= len(s) <= 200]
        if sentences:
            out.setdefault(key, []).extend(sentences[:per_section])
    return {k: v[:per_section] for k, v in out.items()}


def pick_exemplars(
    hits: Iterable[tuple[Document, float]],
    *,
    limit: int = 2,
    exclude: Iterable[str] = (),
    per_section: int = 2,
) -> list[dict[str, Any]]:
    """유사도 순 후보에서 조건에 맞는 과제 limit 개 → [{doc_id, status, similarity, sections}]."""
    excluded = set(exclude)
    out: list[dict[str, Any]] = []
    for doc, score in hits:
        if doc.doc_id in excluded or not eligible(doc):
            continue
        sections = section_sentences(doc, per_section=per_section)
        if not sections:
            continue
        out.append(
            {
                "doc_id": doc.doc_id,
                "status": str((doc.raw or {}).get("status") or ""),
                "similarity": round(float(score), 3),
                "sections": sections,
            }
        )
        if len(out) >= limit:
            break
    return out


def exemplar_ids(exemplars: Iterable[dict[str, Any]]) -> set[str]:
    return {str(e.get("doc_id")) for e in exemplars if e.get("doc_id")}
