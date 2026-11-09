"""평가 문제 만들기 규칙 (ADR 0058, 계약 docs/contracts/eval-results.md §2·§3) — 순수 함수.

- 역방향(reverse): 과제 문서의 초록(없으면 본문)에서 **제목의 명사 토큰**(`keywords.query_keywords`
  기준 — 일반어·숫자·한 글자 제외, 조사 제거)을 뺀 글을 문장 단위로 네 칸(현황·원인·한계·목표)에
  나눠 담는다. 가제는 비운다. 정답 = 그 과제 doc_id. 제목 토큰을 뺀 뒤 글이 `min_chars` 보다 짧으면
  재료로 쓰지 않는다.
- 함정(trap): 과제 A 의 앞 절반(대상·문제) + 과제 B 의 뒤 절반(방법·목표). 두 과제의 토큰 자카드가
  `MAX_TRAP_OVERLAP` 이상이면(같은 주제) 함정이 못 되므로 버린다. 두 과제 모두 제목 토큰을 뺀다.
  차단되면 오답(false_block).
- 새 영역(novel): 철도 밖 주제 사전(config/eval.yaml novel_topics)의 아이디어 그대로. 유사 과제가
  없는지는 유스케이스가 규칙 판정으로 미리 확인한다(차단되는 주제는 뺀다).

문서의 제목·초록·본문만 읽는다 — authors·department 같은 사람 칸은 쓰지 않는다. 문제 id 는 doc_id 를
노출하지 않는 해시(정답 doc_id 는 `answers` 에만).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence

from rra.domain.models import Document
from rra.domain.models.eval_problem import IDEA_FIELDS, EvalProblem, NovelTopic
from rra.domain.rules.keywords import KeywordRule, query_keywords, stem, tokens

_SENTENCE_END = re.compile(r"(?<=[.!?。])\s+|\n+")
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
MAX_TRAP_OVERLAP = 0.15  # 토큰 자카드 — 이보다 겹치면 같은 주제라 함정이 못 된다
MAX_FIELD_CHARS = 1800  # ProposalRequest 슬롯 상한(2000) 아래
SLOT_FIELDS = ("current_state", "root_cause", "limitation", "goal")


def project_text(doc: Document) -> str:
    """문제 재료 글 — 초록이 있으면 초록, 없으면 본문. 제목은 넣지 않는다."""
    return (doc.abstract or doc.body or "").strip()


def title_stems(title: str, rule: KeywordRule) -> list[str]:
    """제목의 명사 토큰(어간) — 일반어·숫자·한 글자 제외."""
    return query_keywords(title or "", rule)


def strip_tokens(text: str, stems: Sequence[str]) -> str:
    """글에서 어간이 `stems` 중 하나로 시작하는 어절을 뺀다 (keyword_overlap 과 같은 접두 일치)."""
    if not stems:
        return text

    def keep(tok: str) -> bool:
        s = stem(tok.lower())
        return not any(s.startswith(k) for k in stems)

    out: list[str] = []
    for piece in re.split(r"(\s+)", text):
        if not piece or piece.isspace():
            out.append(piece)
            continue
        words = _TOKEN_RE.findall(piece)
        if words and not all(keep(w) for w in words):
            continue
        out.append(piece)
    return re.sub(r"[ \t]{2,}", " ", "".join(out)).strip()


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text or "") if s and s.strip()]


def split_slots(parts: Sequence[str], n: int = 4) -> list[str]:
    """문장 목록을 n 칸에 차례로 나눈다. 문장이 n 개보다 적으면 긴 문장을 어절 단위로 쪼갠다."""
    items = [p for p in parts if p]
    if not items:
        return [""] * n
    if len(items) < n:
        words = " ".join(items).split()
        if len(words) < n:
            return [*items, *[""] * (n - len(items))][:n]
        items = [" ".join(words[i * len(words) // n : (i + 1) * len(words) // n]) for i in range(n)]
    total = len(items)
    return [" ".join(items[i * total // n : (i + 1) * total // n]) for i in range(n)]


def _clip(text: str) -> str:
    return text[:MAX_FIELD_CHARS].strip()


def problem_id(kind: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join([kind, *parts]).encode("utf-8")).hexdigest()
    return f"{kind}-{digest[:10]}"


def reverse_problem(
    doc: Document, rule: KeywordRule, *, min_chars: int, seed: int = 0
) -> EvalProblem | None:
    """실제 과제 → 제목 단어 없는 아이디어. 글이 짧거나 제목 토큰을 빼고 남는 것이 적으면 None."""
    text = project_text(doc)
    if len(text) < min_chars:
        return None
    stripped = strip_tokens(text, title_stems(doc.title, rule))
    if len(stripped) < min_chars:
        return None
    slots = split_slots(sentences(stripped))
    if not all(slots):
        return None
    request = {"title_hint": "", **dict(zip(SLOT_FIELDS, (_clip(s) for s in slots), strict=True))}
    return EvalProblem(
        id=problem_id("reverse", doc.doc_id, str(seed)),
        kind="reverse",
        request=request,
        answers=[doc.doc_id],
        sources=[doc.source],
    )


def _stem_set(text: str, rule: KeywordRule) -> set[str]:
    return {t for t in tokens(text) if len(t) >= 2 and t not in rule.generic_terms}


def token_jaccard(a: str, b: str, rule: KeywordRule) -> float:
    sa, sb = _stem_set(a, rule), _stem_set(b, rule)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def trap_problem(
    a: Document, b: Document, rule: KeywordRule, *, min_chars: int, seed: int = 0
) -> EvalProblem | None:
    """A 의 대상·문제(앞 절반) × B 의 방법·목표(뒤 절반). 두 과제가 같은 주제면 None."""
    ta, tb = project_text(a), project_text(b)
    if len(ta) < min_chars or len(tb) < min_chars:
        return None
    if token_jaccard(f"{a.title} {ta}", f"{b.title} {tb}", rule) >= MAX_TRAP_OVERLAP:
        return None
    sa = sentences(strip_tokens(ta, title_stems(a.title, rule)))
    sb = sentences(strip_tokens(tb, title_stems(b.title, rule)))
    if len(sa) < 2 or len(sb) < 2:
        return None
    head = sa[: max(1, len(sa) // 2)]
    tail = sb[len(sb) // 2 :]
    current, cause = split_slots(head, 2)
    limitation, goal = split_slots(tail, 2)
    if not (current and cause and limitation and goal):
        return None
    return EvalProblem(
        id=problem_id("trap", a.doc_id, b.doc_id, str(seed)),
        kind="trap",
        request={
            "title_hint": "",
            "current_state": _clip(current),
            "root_cause": _clip(cause),
            "limitation": _clip(limitation),
            "goal": _clip(goal),
        },
        answers=[a.doc_id, b.doc_id],
        sources=sorted({a.source, b.source}),
    )


def novel_problem(topic: NovelTopic, *, seed: int = 0) -> EvalProblem:
    request = {k: getattr(topic, k) for k in IDEA_FIELDS}
    return EvalProblem(
        id=problem_id("novel", topic.goal, str(seed)),
        kind="novel",
        request=request,
        answers=[],
        sources=["topic"],
    )


def answer_hit(answers: Sequence[str], ranked_ids: Sequence[Sequence[str]], k: int = 5) -> bool:
    """정답 doc_id 가 상위 k 행 안에 있는가. 행 하나는 그 행의 모든 doc_id(대표 + 합친 판)."""
    want = set(answers)
    return any(want & set(row) for row in list(ranked_ids)[:k])
