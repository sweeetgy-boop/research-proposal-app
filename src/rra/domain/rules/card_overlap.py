"""② 차별화 과제안 카드의 겹침 재판정 규칙 (2026-10-28 밤 레인 A, ADR 0039) — 순수 함수.

옛 경고("기존 과제 n건과 가깝다")는 카드 글로 e5 검색을 다시 돌려 차단된 문서 수였다. e5 는 철도
문서끼리 0.85~0.86 에 몰려 거의 모든 카드가 경고를 받았다. 이제 ② 판정과 같은 기준을 쓴다:
카드 글로 규칙 판정(reranker ≥ 0.5 + 아이디어 핵심 키워드 ≥ 1)을 돌려 걸린 과제(카드마다 최대 3건)를
Argon 이 한 번에 "대상·문제·방법이 같은가" 판정 → "같다" 면 겹침.

- 겹친 카드는 보이기 전에 그 카드만 한 번 다시 받는다(겹치는 점을 피하라는 지시, `overlap_hint`).
  다시 받아도 겹치면 경고에 가까운 과제 1~2건 제목과 판정의 한 줄 겹치는 점을 보인다(판정이 이유를
  주지 않으면 제목만 — 지어내지 않는다).
- AI 확인이 실패하면(오류 응답) 규칙에 걸린 과제를 "규칙 기준" 경고로 보이고 다시 받지 않는다.
- 차별성 정렬: 카드의 가까움 = 판정한 후보마다 reranker 점수 + 판정 가중치(같다 1.0·일부 겹침 0.5·
  다르다 0, 규칙 기준 0.5) 중 최댓값, 판정할 후보가 없으면 카드 글 검색의 최고 reranker 점수 × 0.5.
  가까움이 낮은 카드(가장 다른 안)부터. 차별성 판단: 같다가 있으면 낮음, 가까움 ≥ 1.0 이면 보통,
  아니면 높음 (판단 — 화면에 "판단" 표시).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, Field

from rra.domain.models import OverlapAlert
from rra.domain.rules.same_judgment import clean_reason
from rra.domain.rules.trust import escape_untrusted, normalize_evidence_id

MAX_PER_CARD = 3
MAX_WARN = 2
VERDICT_WEIGHT: dict[str, float] = {"same": 1.0, "partial": 0.5, "different": 0.0}
RULE_WEIGHT = 0.5  # AI 확인 실패 — 규칙에 걸린 과제
UNJUDGED_RATIO = 0.5  # 규칙에 걸리지 않은 가장 가까운 과제
_VERDICTS = {
    "same": "same",
    "같다": "same",
    "partial": "partial",
    "일부 겹침": "partial",
    "different": "different",
    "다르다": "different",
}
DIFFERENCE_LABELS: dict[str, str] = {"high": "높음", "mid": "보통", "low": "낮음"}


class CardCheck(BaseModel):
    """카드 하나의 겹침 확인 결과."""

    candidates: list[OverlapAlert] = Field(default_factory=list)  # 규칙에 걸린 과제 (판정 대상)
    nearest: float = 0.0  # 카드 글 검색의 최고 reranker 점수 (판정 대상이 없을 때 정렬용)
    verdicts: dict[str, tuple[str, str]] = Field(default_factory=dict)  # doc_id → (판정, 이유)
    by: str | None = None  # argon | local | rule | None(판정 대상 없음)

    def overlaps(self) -> list[OverlapAlert]:
        """겹치는 과제 — AI "같다", AI 확인 실패면 규칙에 걸린 과제. 가까운 순."""
        if self.by == "rule":
            return list(self.candidates)
        return [a for a in self.candidates if self.verdicts.get(a.doc_id, ("", ""))[0] == "same"]

    @property
    def ai_overlap(self) -> bool:
        """다시 받을 대상 — AI 가 "같다" 로 본 과제가 있다."""
        return self.by in ("argon", "local") and bool(self.overlaps())


def card_id(index: int) -> str:
    return f"c{index + 1}"


def pick_candidates(
    alerts: Sequence[OverlapAlert], limit: int = MAX_PER_CARD
) -> list[OverlapAlert]:
    """규칙에 걸린(rule_blocking) 과제 중 reranker 점수 높은 순 상위 limit 건."""
    hit = [a for a in alerts if (a.rule_blocking if a.rule_blocking is not None else a.blocking)]
    hit.sort(key=lambda a: -(a.rerank_score if a.rerank_score is not None else a.similarity))
    return hit[:limit]


def nearest_score(alerts: Sequence[OverlapAlert]) -> float:
    scores = [a.rerank_score for a in alerts if a.rerank_score is not None]
    return max(scores) if scores else 0.0


def parse_card_verdicts(
    data: Mapping[str, Any] | None, allowed: Mapping[str, Sequence[str]]
) -> dict[str, dict[str, tuple[str, str]]] | None:
    """LLM JSON {"items": [{card, doc_id, verdict, reason}]} → {card: {doc_id: (판정, 이유)}}.

    보낸 (카드, 과제) 쌍 밖은 버린다(보안 A). 하나도 못 읽으면 None(실패)."""
    if not isinstance(data, Mapping):
        return None
    items = data.get("items")
    if not isinstance(items, list):
        return None
    total = sum(len(v) for v in allowed.values())
    out: dict[str, dict[str, tuple[str, str]]] = {}
    for raw in items[: max(1, total) * 2]:
        if not isinstance(raw, Mapping):
            continue
        card = str(raw.get("card", "")).strip()
        doc_id = normalize_evidence_id(str(raw.get("doc_id", "")))
        verdict = _VERDICTS.get(str(raw.get("verdict", "")).strip().lower())
        if card not in allowed or doc_id not in allowed[card] or verdict is None:
            continue
        out.setdefault(card, {}).setdefault(doc_id, (verdict, clean_reason(raw.get("reason"))))
    return out or None


def closeness(check: CardCheck) -> float:
    """정렬용 가까움 — 낮을수록 기존 과제와 다르다 (모듈 설명)."""
    if not check.candidates:
        return round(check.nearest * UNJUDGED_RATIO, 4)
    values = []
    for a in check.candidates:
        score = a.rerank_score if a.rerank_score is not None else a.similarity
        if check.by == "rule":
            weight = RULE_WEIGHT
        else:
            verdict = check.verdicts.get(a.doc_id, ("", ""))[0]
            weight = VERDICT_WEIGHT.get(verdict, RULE_WEIGHT)
        values.append(score + weight)
    return round(max(values), 4)


def difference_level(check: CardCheck) -> str:
    """차별성 판단 — 같다가 있으면 낮음, 가까움 ≥ 1.0 이면 보통, 아니면 높음."""
    if check.overlaps():
        return "low"
    return "mid" if closeness(check) >= 1.0 else "high"


def warning_fields(check: CardCheck) -> dict[str, Any]:
    """카드의 겹침 경고 칸 — 가까운 과제 1~2건 doc_id·제목 + 판정의 한 줄 겹치는 점
    (없으면 빈 값)."""
    close = check.overlaps()[:MAX_WARN]
    reason = ""
    if check.by in ("argon", "local"):
        for a in close:
            reason = check.verdicts.get(a.doc_id, ("", ""))[1]
            if reason:
                break
    return {
        "overlap_warning": [a.doc_id for a in close],
        "overlap_titles": [a.title for a in close],
        "overlap_reason": reason,
        "overlap_by": check.by,
        "closeness": closeness(check),
        "difference": difference_level(check),
    }


def overlap_hint(card: Any, check: CardCheck) -> str:
    """겹친 카드 하나를 다시 받을 때 모델에 주는 지시 — 겹친 과제 제목·겹치는 점(판정 출력, 비신뢰 →
    escape)."""
    lines = []
    for a in check.overlaps()[:MAX_WARN]:
        reason = check.verdicts.get(a.doc_id, ("", ""))[1]
        point = f" — 겹치는 점: {escape_untrusted(reason)}" if reason else ""
        lines.append(f"- 기존 과제 「{escape_untrusted(a.title)}」{point}")
    return (
        "[겹침을 피해 다시 쓸 안] 아래 과제안은 기존 과제와 대상·문제·방법이 같다고 판정됐다.\n"
        f"가제: {escape_untrusted(card.title)}\n요약: {escape_untrusted(card.summary)}\n"
        + "\n".join(lines)
        + "\n겹치는 부분(같은 대상·같은 방법)을 피해 이 안 하나만 다시 쓴다. "
        "아이디어의 목적 안에서, "
        "자료·입력에 없는 수치·정책명을 쓰지 않는다. recommendations 에 1개만."
    )


def shown_hint(cards: Sequence[Any]) -> str:
    """[차별화 과제안 더 만들기] — 이미 보인 안과 다른 안만 받는 지시
    (가제·요약만, 비신뢰 → escape)."""
    lines = [
        f"- {escape_untrusted(c.title)}: {escape_untrusted(c.summary)}" for c in cards if c.title
    ]
    return (
        "[이미 보인 과제안] 아래 안은 이미 제안자에게 보였다. "
        "이것들과 대상·방법이 다른 새 안만 쓴다 "
        "(같은 안을 말만 바꿔 다시 쓰지 않는다).\n" + "\n".join(lines)
    )
