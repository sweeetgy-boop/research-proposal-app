"""정책 문구 고르기·정책 근거 칸 채우기 (순수).

- pick_quote: 청크에서 질의 키워드가 가장 많이 겹치는 문장 하나 (300자 이내, 문장 통째로).
  인용 정리(2026-10-28 레인 B): 글 안의 긴 URL 은 지우고(원문 링크는 화면 아래 "원문"), 앞 글머리
  ("O 이에", "?", "-", "○", "□", 번호)는 떼며, 문장 중간에서 자르지 않는다.
- policy_basis_text: 제안자가 고른 추천 → "문구 (문서명, 연도, 위치, URL)". 자동으로 넣지 않는다 —
  진입점은 제안자가 고른 뒤에만 apply_policy_suggestion 을 부른다.
정책적 중요도 섹션의 근거 규칙은 그대로다 (policy_basis 입력만 근거, rules.yaml evidence_forbidden).
"""

from __future__ import annotations

import re

from rra.domain.models import MAX_SUGGESTIONS, PolicySuggestion, ProposalRequest
from rra.domain.models.policy import MAX_QUOTE
from rra.domain.rules.keywords import KeywordRule, keyword_overlap

# 문장 경계 — 마침표류 뒤 공백, 줄바꿈, 본문 중간의 글머리 기호(○ □ ■ ◦ • ▶ ※, 영문 O 글머리)
_SENT = re.compile(r"(?<=[.!?。])\s+|\n+|\s+(?=[○●□■◦•▶▷※]\s)|(?<=[가-힣.])\s+(?=[Oo]\s+[가-힣])")
MIN_SENT = 12
# 원문 링크는 인용 아래 "원문" 링크로만 — 인용 글 안의 긴 주소는 지운다
_URL_PAREN = re.compile(r"[(（]\s*(?:https?://|www\.)[^)）]*[)）]")
_URL = re.compile(r"(?:https?://|www\.)\S+")
# 문장 앞 글머리: ○ □ - ? · ※ ▶, 영문 O·ㅇ 글머리, 번호(1. 1) (1) 가. ①), 이어 주는 말(이에·따라서
# …)
_LEAD = re.compile(
    r"\A\s*(?:[○●□■◦•·▪▶▷※\-–—?*ㅇ]+|[Oo](?=\s)|[(（]?\d{1,2}[.)）]|[(（]\d{1,2}[)）]"
    r"|[(（]?[가-하][.)）]|[①-⑳])\s*"
)
_CONNECTIVE = re.compile(r"\A(?:이에\s*따라|이에|이를\s*위해|따라서|또한|아울러|한편|그리고)[,\s]+")
# 문장 끝 — 마침표류, 또는 개조식 종결(~다/~음/~함/~임 + 끝)
_END = re.compile(r"(?:[.!?。]|[다음함임됨있없]\s*[.]?)\s*\Z")


def strip_urls(text: str) -> str:
    """인용 글 안의 URL(괄호째) 제거 + 공백 정리."""
    text = _URL_PAREN.sub(" ", text)
    text = _URL.sub(" ", text)
    return " ".join(text.split())


def clean_quote(text: str) -> str:
    """인용 한 문장 정리 — URL 제거, 앞 글머리·번호·이어 주는 말 떼기. 글자는 원문 그대로(가운데는
    고치지 않는다)."""
    body = strip_urls(text)
    for _ in range(3):
        stripped = _CONNECTIVE.sub("", _LEAD.sub("", body)).strip()
        if stripped == body:
            break
        body = stripped
    return body


def match_text(text: str) -> str:
    """원문 대조용 — URL 을 지우고 공백을 모두 뺀 글. 인용(clean_quote)이 원문에 있는지 볼 때 양쪽에
    같이 쓴다(verify_sources)."""
    return "".join(strip_urls(text).split())


def is_complete(sentence: str) -> bool:
    return bool(_END.search(sentence))


def sentences(text: str) -> list[str]:
    """정리된 문장 목록 (URL·글머리 제거, 너무 짧은 조각 제외)."""
    out = []
    for part in _SENT.split(text):
        body = clean_quote(part)
        if len(body) >= MIN_SENT:
            out.append(body)
    return out


def pick_quote(text: str, query: str, rule: KeywordRule | None = None) -> tuple[str, list[str]]:
    """(문장, 겹친 키워드). 문장은 통째로만 — 300자를 넘는 문장은 자르지 않고 후보에서 뺀다
    (문장 중간에서 끊지 않는다). 겹침이 없으면 첫 문장. 맞는 문장이 없으면 ("", [])."""
    rule = rule or KeywordRule()
    best, best_hits = "", []
    parts = sentences(text)
    if len(parts) > 1 and not is_complete(strip_urls(text)):
        parts = parts[:-1]  # 청크 끝에서 잘린 조각은 고르지 않는다
    for sent in parts:
        if len(sent) > MAX_QUOTE:
            continue
        hits = keyword_overlap(query, sent, rule)
        if len(hits) > len(best_hits) or not best:
            best, best_hits = sent, hits
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
