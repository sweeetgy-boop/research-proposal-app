"""문제 정의 카드 수정 기록·본인 예시 (ADR 0065, 계약 problem-card.md 6절). 순수 함수.

- 수정 짝(card_edits.jsonl) 한 줄: 허용 칸만. 글은 이름·연락처를 지운 뒤 남긴다.
- 변경 전후 의미 유사도가 `polish_similarity` 이상이면 표현 다듬기 — 줄은 남기되(유사도 값이 표시)
  학습(본인 예시)에서는 뺀다.
- 본인 예시: 그 사용자의 줄 중 시험 줄·다듬기 줄을 빼고, 지금 입력과 비슷한 순으로 상위 N 건.
  **다른 사용자 줄은 어떤 경우에도 고르지 않는다**(저장소가 걸러 주더라도 여기서 한 번 더 본다).
- 선택 기록(similar_choices.jsonl)의 `event: "card_edit"` 줄: 글은 80자 요약.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from rra.domain.rules.privacy import strip_personal

EVENT_CARD_EDIT = "card_edit"
SUMMARY_CHARS = 80
EDIT_TEXT_CHARS = 300
EDIT_KEYS = frozenset(
    {
        "at",
        "user",
        "test",
        "idea",
        "field",
        "before",
        "after",
        "similarity",
        "function",
        "methods",
        "signals",
    }
)
# 선택 기록 파일에 card_edit 줄이 더하는 칸 (choice_log.ALLOWED_KEYS 에 합친다)
CHOICE_LINE_EXTRA_KEYS = frozenset({"field", "before", "after", "methods", "signals"})


NAME_MARK = "[이름]"


def strip_contacts(text: str) -> str:
    """카드 글에서 이름·연락처를 지운다(`rules/privacy`).

    privacy 의 '부서 + 이름' 규칙은 문서 본문용이라 카드의 짧은 구("차단 효과"·"미관과 유지관리")를
    부서 뒤 이름으로 보고 뒷말을 지울 수 있다. 그 규칙이 걸린 것으로 보이면(이름을 지웠다는데
    표식이 그만큼 없다) 낱말을 잃지 않게 어절마다 따로 지운다 — 전화·이메일·번호는 그대로 지워진다.
    """
    report = strip_personal(text or "")
    names = report.removed.get("name", 0)
    if names and report.text.count(NAME_MARK) < names:
        return " ".join(strip_personal(w).text for w in (text or "").split())
    return report.text


def _safe(text: str, limit: int) -> str:
    return " ".join(strip_contacts(text).split())[:limit]


def cosine(a: Sequence[float], b: Sequence[float]) -> float | None:
    """두 벡터의 코사인 유사도. 길이가 다르거나 영벡터면 None."""
    if not a or len(a) != len(b):
        return None
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    if not na or not nb:
        return None
    return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb)


def is_polish(similarity: object, threshold: float) -> bool:
    """표현 다듬기인가 — 변경 전후 의미 유사도가 임계치 이상. 유사도를 모르면 아니다."""
    return (
        isinstance(similarity, (int, float))
        and not isinstance(similarity, bool)
        and similarity >= threshold
    )


def edit_record(
    *,
    at: str,
    user: str,
    test: bool,
    idea: str,
    field: str,
    before: str,
    after: str,
    similarity: float | None,
    function: str,
    methods: Sequence[str],
    signals: Sequence[str],
) -> dict[str, Any]:
    """수정 짝 한 줄 — 가명 ID·해시·항목 이름·변경 전후 글(개인정보 제거)."""
    return {
        "at": at,
        "user": user,
        "test": bool(test),
        "idea": idea,
        "field": field,
        "before": _safe(before, EDIT_TEXT_CHARS),
        "after": _safe(after, EDIT_TEXT_CHARS),
        "similarity": None if similarity is None else round(float(similarity), 4),
        "function": _safe(function, EDIT_TEXT_CHARS),
        "methods": [str(m) for m in methods],
        "signals": [str(s) for s in signals],
    }


def choice_line(
    *,
    at: str,
    idea: str,
    field: str,
    before: str,
    after: str,
    methods: Sequence[str],
    signals: Sequence[str],
    test: bool,
) -> dict[str, Any]:
    """선택 기록 파일의 card_edit 줄 — 글은 80자 요약. 시험 계정 줄만 `test: true`."""
    line: dict[str, Any] = {
        "at": at,
        "event": EVENT_CARD_EDIT,
        "idea": idea,
        "field": field,
        "before": _safe(before, SUMMARY_CHARS),
        "after": _safe(after, SUMMARY_CHARS),
        "methods": [str(m) for m in methods],
        "signals": [str(s) for s in signals],
    }
    if test:
        line["test"] = True
    return line


def example_text(record: Mapping[str, Any]) -> str:
    """수정 짝을 지금 입력과 견줄 때 쓰는 글 — 당시 기능 문장 + 고치기 전 글."""
    return " ".join(str(record.get(k) or "") for k in ("function", "before")).strip()


def learnable(
    records: Sequence[Mapping[str, Any]], *, user: str, polish_similarity: float
) -> list[Mapping[str, Any]]:
    """본인 예시 후보 — 그 사용자의 줄만, 시험 줄·다듬기 줄·빈 글 제외."""
    return [
        r
        for r in records
        if user
        and r.get("user") == user
        and r.get("test") is not True
        and not is_polish(r.get("similarity"), polish_similarity)
        and str(r.get("after") or "").strip()
        and str(r.get("before") or "") != str(r.get("after") or "")
    ]


def pick_examples(
    records: Sequence[Mapping[str, Any]],
    similarities: Sequence[float | None],
    *,
    user: str,
    min_similarity: float,
    polish_similarity: float,
    limit: int,
) -> list[Mapping[str, Any]]:
    """후보 줄과 '지금 입력과의 유사도'(같은 순서) → 상위 limit 건. 임계치 미만·모름은 뺀다."""
    if limit <= 0:
        return []
    ok = {id(r) for r in learnable(records, user=user, polish_similarity=polish_similarity)}
    scored = [
        (float(s), i, r)
        for i, (r, s) in enumerate(zip(records, similarities, strict=False))
        if id(r) in ok and s is not None and s >= min_similarity
    ]
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [r for _, _, r in scored[:limit]]


def examples_block(examples: Sequence[Mapping[str, Any]], labels: Mapping[str, str]) -> str:
    """지시문 `[이 제안자가 전에 고친 예]` 구획의 본문(없으면 빈 문자열)."""
    lines = []
    for r in examples:
        name = labels.get(str(r.get("field")), "항목")
        before = _safe(str(r.get("before") or ""), EDIT_TEXT_CHARS) or "(빈칸)"
        lines.append(f"- {name}: {before} → {_safe(str(r.get('after') or ''), EDIT_TEXT_CHARS)}")
    return "\n".join(lines)
