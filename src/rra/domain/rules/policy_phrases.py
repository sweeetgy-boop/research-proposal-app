"""정책 문구 고르기·정책 근거 칸 채우기 (순수).

- pick_quote / pick_passage: 청크에서 질의 키워드가 가장 많이 겹치는 문장 하나 (300자 이내, 문장
  통째로).
  인용 정리(2026-10-28 레인 B): 글 안의 긴 URL 은 지우고(원문 링크는 화면 아래 "원문"), 앞 글머리
  ("O 이에", "?", "-", "○", "□", 번호)는 떼며, 문장 중간에서 자르지 않는다.
- 잘린 인용 고치기(2026-11-09 레인 B, ADR 0061): PDF 추출 글의 각주 번호(단어 끝에 붙은 1~3자리 숫자
  + ")", 위첨자 숫자)·줄 끝 하이픈을 걸러 내고(normalize_pdf), 청크가 문장 중간에서 시작·끝나면 문서
  본문 안에서 앞뒤 문장 경계까지 넓힌다(widen_to_sentences). 넓혀도 불완전한 문장(조사·소문자로
  시작,
  문장 끝 없음, 너무 짧음)은 버리지 않고 뒤로 미룬다 — Passage.complete 가 거짓이면 순위가 내려간다
  (rank, PolicyCards.passages).
- policy_basis_text: 제안자가 고른 추천 → "문구 (문서명, 연도, 위치)" — URL 은 넣지 않는다. 자동으로
넣지 않는다 —
  진입점은 제안자가 고른 뒤에만 apply_policy_suggestion 을 부른다.
정책적 중요도 섹션의 근거 규칙은 그대로다 (policy_basis 입력만 근거, rules.yaml evidence_forbidden).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

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

# ── PDF 추출 흔적 (2026-11-09) ──
# 각주 번호 — 글자(한글·영문·닫는 괄호·따옴표) 바로 뒤에 붙은 1~3자리 숫자 + ")"
# (예: "하자보수73)하였으나").
# 줄 머리 번호 "1) …"(앞에 글자가 없음)·연도 "2023)"(4자리)은 건드리지 않는다
_FOOTNOTE = re.compile(r"(?<=[가-힣a-zA-Z\)）\]”’'\"])(?<!제)\d{1,3}\)(?!\d)")
_SUPERSCRIPT = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+")
# PDF 줄 끝 하이픈 — "유지-\n보수" → "유지보수"
_HYPHEN_BREAK = re.compile(r"(?<=[가-힣a-zA-Z])-[ \t]*\n[ \t]*(?=[가-힣a-zA-Z])")
# 문장 머리가 조각인 표시 — 조사·어미로 시작(앞 문장이 잘림), 영문 소문자로 시작
_FRAGMENT_START = re.compile(
    r"\A(?:[은는을를의에로와과도만]|에서|으로|부터|까지|에게|이며|하며|하고|하여|되어|으나|지만)(?=\s|[,.])"
    r"|\A[a-z]"
)
# 문장 경계(본문 안에서 앞으로 넓힐 때) — 마침표류 뒤 공백, 줄바꿈, 글머리 기호 앞
_BOUNDARY = re.compile(r"[.!?。]\s+|\n|(?<=\s)(?=[○●□■◦•▶▷※]\s)")
# 문장 끝(본문 안에서 뒤로 넓힐 때) — 마침표류(뒤가 공백·끝) 또는 줄바꿈
_FORWARD_END = re.compile(r"[.!?。](?=\s|\Z)|\n")
WIDEN_MARGIN = 400


@dataclass(frozen=True)
class Passage:
    """청크에서 고른 인용 한 문장. complete 가 거짓이면 문장이 온전하지 않다(앞이 조사·소문자로
    시작,
    문장 끝 없음, 너무 짧음) — 버리지 않고 순위를 내린다."""

    quote: str
    hits: list[str] = field(default_factory=list)
    complete: bool = True


def normalize_pdf(text: str) -> str:
    """PDF 추출 흔적 제거 — 줄 끝 하이픈 잇기, 각주 번호·위첨자 숫자 지우기. 글자 자체는 바꾸지
    않는다."""
    text = _HYPHEN_BREAK.sub("", text)
    text = _FOOTNOTE.sub("", text)
    return _SUPERSCRIPT.sub("", text)


def strip_urls(text: str) -> str:
    """인용 글 안의 URL(괄호째) 제거 + 공백 정리."""
    text = _URL_PAREN.sub(" ", text)
    text = _URL.sub(" ", text)
    return " ".join(text.split())


def clean_text(text: str) -> str:
    """PDF 흔적(각주·하이픈) + URL 제거 + 공백 정리 — 인용·원문 대조 양쪽이 같이 쓴다."""
    return strip_urls(normalize_pdf(text))


def clean_quote(text: str) -> str:
    """인용 한 문장 정리 — URL·각주 제거, 앞 글머리·번호·이어 주는 말 떼기. 글자는 원문
    그대로(가운데는
    고치지 않는다)."""
    body = clean_text(text)
    for _ in range(3):
        stripped = _CONNECTIVE.sub("", _LEAD.sub("", body)).strip()
        if stripped == body:
            break
        body = stripped
    return body


def match_text(text: str) -> str:
    """원문 대조용 — URL·각주를 지우고 공백을 모두 뺀 글. 인용(clean_quote)이 원문에 있는지 볼 때
    양쪽에
    같이 쓴다(verify_sources)."""
    return "".join(clean_text(text).split())


def is_complete(sentence: str) -> bool:
    return bool(_END.search(sentence))


def is_fragment(sentence: str) -> bool:
    """문장이 조각인가 — 조사·어미나 영문 소문자로 시작(앞이 잘림), 문장 끝이 없음, 너무 짧음."""
    body = sentence.strip()
    return len(body) < MIN_SENT or bool(_FRAGMENT_START.match(body)) or not is_complete(body)


def sentences(text: str) -> list[str]:
    """정리된 문장 목록 (URL·글머리 제거, 너무 짧은 조각 제외)."""
    out = []
    for part in _SENT.split(normalize_pdf(text)):
        body = clean_quote(part)
        if len(body) >= MIN_SENT:
            out.append(body)
    return out


def _ws(text: str) -> str:
    """줄바꿈은 두고 가로 공백만 하나로 — 본문 안에서 청크를 찾을 때 양쪽에 같이 쓴다."""
    return re.sub(r"[ \t ]+", " ", normalize_pdf(text)).strip()


def widen_to_sentences(
    body: str | None, chunk: str, *, margin: int = WIDEN_MARGIN
) -> tuple[str, bool]:
    """청크를 문서 본문 안에서 찾아 앞은 직전 문장 경계(마침표 뒤·줄바꿈·글머리), 뒤는 다음 문장
    끝까지
    넓힌다(각 margin 자 안에서). (넓힌 글, 본문에서 찾았는가). 못 찾으면 청크 그대로·False."""
    if not body or not chunk.strip():
        return chunk, False
    hay, needle = _ws(body), _ws(chunk)
    idx = hay.find(needle)
    if idx < 0:  # 줄바꿈 처리가 달라 못 찾으면 공백을 모두 하나로
        hay = " ".join(hay.split())
        needle = " ".join(needle.split())
        idx = hay.find(needle)
        if idx < 0:
            return chunk, False
    end = idx + len(needle)
    start = idx
    seg_start = max(0, idx - margin)
    before = hay[seg_start:idx]
    boundaries = [m.end() for m in _BOUNDARY.finditer(before)]
    if boundaries:
        start = seg_start + boundaries[-1]
    elif seg_start == 0:
        start = 0
    after = hay[end : end + margin]
    m = _FORWARD_END.search(after)
    if m:
        end = end + m.end()
    elif end + margin >= len(hay):
        end = len(hay)
    return hay[start:end].strip(), True


def pick_passage(
    text: str, query: str, rule: KeywordRule | None = None, *, body: str | None = None
) -> Passage:
    """청크에서 인용 한 문장 — body(문서 본문)가 있으면 먼저 문장 경계까지 넓힌다. 문장은 통째로만
    (300자를 넘는 문장은 뺀다). 고르는 순서: 질의 키워드가 겹치는 문장 > 온전한 문장 > 겹친 키워드
    수 >
    앞에 있는 문장. 맞는 문장이 없으면 quote "". complete 는 고른 문장이 온전한지."""
    rule = rule or KeywordRule()
    widened, anchored = widen_to_sentences(body, text)
    parts = [p for p in _SENT.split(normalize_pdf(widened)) if p.strip()]
    tail_cut = not anchored and len(parts) > 1 and not is_complete(clean_text(widened))
    best: tuple[tuple[bool, bool, int, int], Passage] | None = None
    for i, raw in enumerate(parts):
        sent = clean_quote(raw)
        if len(sent) < MIN_SENT or len(sent) > MAX_QUOTE:
            continue
        complete = not is_fragment(sent)
        if i == len(parts) - 1 and tail_cut:
            complete = False  # 청크 끝에서 잘린 조각 — 본문에서 못 넓혔다
        hits = keyword_overlap(query, sent, rule)
        key = (bool(hits), complete, len(hits), -i)
        if best is None or key > best[0]:
            best = (key, Passage(quote=sent, hits=hits, complete=complete))
    return best[1] if best else Passage(quote="", hits=[], complete=False)


def pick_quote(
    text: str, query: str, rule: KeywordRule | None = None, *, body: str | None = None
) -> tuple[str, list[str]]:
    """(문장, 겹친 키워드) — pick_passage 의 옛 모양."""
    p = pick_passage(text, query, rule, body=body)
    return p.quote, p.hits


def rank(suggestions: list[PolicySuggestion]) -> list[PolicySuggestion]:
    """온전한 문장 먼저 → 키워드 겹침 많은 순 → 유사도 순. 같은 문서는 한 번. 최대 MAX_SUGGESTIONS.
    불완전한 인용(complete=False)은 버리지 않고 뒤로 간다."""
    seen: set[str] = set()
    out: list[PolicySuggestion] = []
    for s in sorted(
        suggestions,
        key=lambda s: (not s.complete, -len(s.keywords), -(s.similarity or 0.0), s.doc_id),
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
    # 긴 원문 URL 은 넣지 않는다 — 원문 링크는 화면의 "원문" (2026-10-28 레인 B, ADR 0040)
    src = f"{s.title}" + (f", {where}" if where else "")
    return f"“{s.quote}” ({src})"


def apply_policy_suggestion(req: ProposalRequest, s: PolicySuggestion) -> ProposalRequest:
    """제안자가 고른 문구를 policy_basis 에 덧붙인다 (기존 입력은 유지). 길이 상한은 모델이 강제."""
    line = policy_basis_text(s)
    merged = f"{req.policy_basis}\n{line}".strip() if req.policy_basis else line
    return req.model_copy(update={"policy_basis": merged})
