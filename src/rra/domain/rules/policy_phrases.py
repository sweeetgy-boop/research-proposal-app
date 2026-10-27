"""정책 문구 고르기·정책 근거 칸 채우기 (순수).

- pick_quote: 청크에서 질의 키워드가 가장 많이 겹치는 문장 하나 (있는 그대로, 300자 이내).
- policy_basis_text: 제안자가 고른 추천 → "문구 (문서명, 연도, 위치, URL)". 자동으로 넣지 않는다 —
  진입점은 제안자가 고른 뒤에만 apply_policy_suggestion 을 부른다.
정책적 중요도 섹션의 근거 규칙은 그대로다 (policy_basis 입력만 근거, rules.yaml evidence_forbidden).
"""

from __future__ import annotations

import re

from rra.domain.models import MAX_SUGGESTIONS, PolicySuggestion, ProposalRequest
from rra.domain.models.policy import MAX_QUOTE
from rra.domain.rules.keywords import KeywordRule, keyword_overlap

_SENT = re.compile(r"(?<=[.!?。])\s+|\n+")
MIN_SENT = 12


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text) if len(s.strip()) >= MIN_SENT]


def pick_quote(text: str, query: str, rule: KeywordRule | None = None) -> tuple[str, list[str]]:
    """(문장, 겹친 키워드). 겹침이 없으면 첫 문장. 300자를 넘으면 앞부분만 + '…'."""
    rule = rule or KeywordRule()
    best, best_hits = "", []
    for sent in sentences(text):
        hits = keyword_overlap(query, sent, rule)
        if len(hits) > len(best_hits) or not best:
            best, best_hits = sent, hits
    if not best:
        best = " ".join(text.split())[:MAX_QUOTE]
    if len(best) > MAX_QUOTE:
        best = best[: MAX_QUOTE - 1] + "…"
    return best, best_hits


def rank(suggestions: list[PolicySuggestion]) -> list[PolicySuggestion]:
    """키워드 겹침 많은 순 → 유사도 순. 같은 문서는 한 번. 최대 MAX_SUGGESTIONS."""
    seen: set[str] = set()
    out: list[PolicySuggestion] = []
    for s in sorted(
        suggestions, key=lambda s: (-len(s.keywords), -(s.similarity or 0.0), s.doc_id)
    ):
        if s.doc_id in seen:
            continue
        seen.add(s.doc_id)
        out.append(s)
        if len(out) >= MAX_SUGGESTIONS:
            break
    return out


def policy_basis_text(s: PolicySuggestion) -> str:
    where = ", ".join(p for p in (str(s.year) if s.year else "", s.page or "") if p)
    src = f"{s.title}" + (f", {where}" if where else "") + (f", {s.url}" if s.url else "")
    return f"“{s.quote}” ({src})"


def apply_policy_suggestion(req: ProposalRequest, s: PolicySuggestion) -> ProposalRequest:
    """제안자가 고른 문구를 policy_basis 에 덧붙인다 (기존 입력은 유지). 길이 상한은 모델이 강제."""
    line = policy_basis_text(s)
    merged = f"{req.policy_basis}\n{line}".strip() if req.policy_basis else line
    return req.model_copy(update={"policy_basis": merged})
