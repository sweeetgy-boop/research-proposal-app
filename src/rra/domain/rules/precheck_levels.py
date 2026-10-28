"""② 유사과제 표의 판정·관련도·기본 선택 규칙 (2026-10-28 밤 레인 A, ADR 0039) — 순수 함수.

- 판정 칸은 AI 같음 판정을 따른다: 같다 → 차단, 일부 겹침 → 근접, 다르다 → 관련 낮음. AI 판정이
  오기 전(또는 실패)에는 규칙 판정(점수 + 핵심 키워드)을 "규칙 기준" 으로 보인다: 규칙 차단 → 차단,
  아니면 근접.
- 관련도는 reranker 점수 하나만 쉬운 말로: 높음(≥ 0.8) · 보통(≥ 0.5 = 규칙 차단 하한) · 낮음.
  e5 유사도는 철도 문서끼리 0.85~0.86 에 몰려 뜻이 없어 화면에 보이지 않는다.
  reranker 가 없으면 관련도도 없다.
- 기본 선택: AI 가 "다르다" 로 본 행만 [관련 없음] 을 미리 고른다. 일부 겹침·같다는 비워 제안자가
  정한다(차단 행은 고르기 전에는 [다음] 이 막힌다 — 종전 게이트 그대로).
- 과제안 근거 행(basis_alerts): [유사함] 으로 고른 행이 있으면 그 행만, 없으면 [관련 없음] 이 아니고
  (선택이 없으면) AI "다르다" 가 아닌 행.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from rra.domain.models import OverlapAlert
from rra.domain.rules.similar_choice import SIMILAR, UNRELATED, choice_for

BLOCKING, NEAR, LOW = "blocking", "near", "low"
LEVEL_LABELS: dict[str, str] = {BLOCKING: "차단", NEAR: "근접", LOW: "관련 낮음"}
_VERDICT_LEVEL: dict[str, str] = {"same": BLOCKING, "partial": NEAR, "different": LOW}
BASIS_LABELS: dict[str, str] = {"ai": "AI 판정", "rule": "규칙 기준"}

RELEVANCE_HIGH = 0.8
RELEVANCE_MID = 0.5
RELEVANCE_LABELS: dict[str, str] = {"high": "높음", "mid": "보통", "low": "낮음"}


def judgment_level(alert: OverlapAlert) -> tuple[str, str]:
    """(판정 단계, 근거) — 근거 ai 는 AI 같음 판정, rule 은 규칙 판정(AI 판정 전·실패·상위 밖)."""
    verdict = getattr(alert, "judgment", None)
    if verdict in _VERDICT_LEVEL:
        return _VERDICT_LEVEL[verdict], "ai"
    return (BLOCKING if alert.blocking else NEAR), "rule"


def relevance_level(score: float | None) -> str | None:
    """reranker 점수 → 높음·보통·낮음 (없으면 None)."""
    if score is None:
        return None
    if score >= RELEVANCE_HIGH:
        return "high"
    if score >= RELEVANCE_MID:
        return "mid"
    return "low"


def default_choices(alerts: Iterable[OverlapAlert]) -> dict[str, str]:
    """AI 가 "다르다" 로 본 행만 [관련 없음] — doc_id → unrelated."""
    return {a.doc_id: UNRELATED for a in alerts if getattr(a, "judgment", None) == "different"}


def basis_alerts(alerts: Sequence[OverlapAlert], choices: Mapping[str, str]) -> list[OverlapAlert]:
    """과제안(차별화 과제 추천)의 비교 대상 행. [유사함] 이 있으면 그것만, 없으면 [관련 없음] 이
    아니고 (고르지 않은 행이면) AI "다르다" 가 아닌 행."""
    similar = [a for a in alerts if choice_for(a, choices) == SIMILAR]
    if similar:
        return similar
    out = []
    for a in alerts:
        choice = choice_for(a, choices)
        if choice == UNRELATED:
            continue
        if choice is None and getattr(a, "judgment", None) == "different":
            continue
        out.append(a)
    return out


def level_view(alert: OverlapAlert) -> dict[str, Any]:
    """화면용 판정·관련도 칸 (views.alerts_payload 가 붙인다)."""
    level, basis = judgment_level(alert)
    rel = relevance_level(getattr(alert, "rerank_score", None))
    return {
        "level": level,
        "level_label": LEVEL_LABELS[level],
        "level_basis": basis,
        "level_basis_label": BASIS_LABELS[basis],
        "relevance": rel,
        "relevance_label": RELEVANCE_LABELS.get(rel or "", None),
    }
