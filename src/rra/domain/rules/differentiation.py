"""기획서 기능 2 — 유사과제 활용·차별화 제안의 순수 규칙 (후보 선정, LLM 출력 검증).

후보: precheck 알림 중 차단(blocking) 또는 기준 근접(유사도 ≥ 티어 임계치 × NEAR_RATIO).
차단 → 유사도 순, 최대 MAX_CANDIDATES 개.
검증: LLM 이 돌려준 항목은 후보 doc_id 에 대한 것만, evidence 는 후보 id 안에서만, 본문은 제안
입력과 겹친 과제 문서에 있는 고유명·수치만(grounding) 쓰고 한자·가나가 없어야 한다. 하나라도
어긋나면 그 항목은 폐기 사유와 함께 버린다 (보안 A: LLM 출력은 비신뢰 → 구획 태그 무력화·길이 상한).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from rra.domain.models import (
    MAX_DIRECTIONS,
    MAX_ITEM_CHARS,
    DifferentiationItem,
    Document,
    OverlapAlert,
    Tier,
)
from rra.domain.rules.foreign_script import has_foreign_script
from rra.domain.rules.grounding import ungrounded
from rra.domain.rules.llm_output import clean_sentence
from rra.domain.rules.overlap import DEFAULT_THRESHOLDS, document_text
from rra.domain.rules.trust import escape_untrusted, normalize_evidence_id

NEAR_RATIO = 0.9
MAX_CANDIDATES = 5
DISCARD_UNKNOWN_DOC = "unknown_doc"
DISCARD_NO_DIRECTION = "no_direction"
DISCARD_EVIDENCE = "evidence_out_of_range"
DISCARD_UNGROUNDED = "ungrounded"
DISCARD_FOREIGN = "foreign_script"
DISCARD_DUPLICATE = "duplicate"


def near_threshold(
    alert: OverlapAlert, thresholds: Mapping[Tier, float] | None = None, ratio: float = NEAR_RATIO
) -> bool:
    floor = (thresholds or DEFAULT_THRESHOLDS)[alert.tier] * ratio
    return alert.similarity + 1e-9 >= floor  # 0.80 × 0.9 = 0.7200000000000001 같은 부동소수 오차


def needs_differentiation(
    alerts: Iterable[OverlapAlert], thresholds: Mapping[Tier, float] | None = None
) -> bool:
    return any(a.blocking or near_threshold(a, thresholds) for a in alerts)


def candidates(
    alerts: Iterable[OverlapAlert],
    thresholds: Mapping[Tier, float] | None = None,
    limit: int = MAX_CANDIDATES,
) -> list[OverlapAlert]:
    """차별화 제안 대상 — 차단 먼저, 그다음 유사도 순. 같은 doc_id 는 한 번."""
    picked: list[OverlapAlert] = []
    seen: set[str] = set()
    for a in sorted(alerts, key=lambda x: (-int(x.blocking), -x.similarity)):
        if a.doc_id in seen or not (a.blocking or near_threshold(a, thresholds)):
            continue
        seen.add(a.doc_id)
        picked.append(a)
        if len(picked) >= limit:
            break
    return picked


def candidate_text(doc: Document, max_chars: int) -> str:
    return document_text(doc)[:max_chars]


def _text(value: Any, limit: int = MAX_ITEM_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    return clean_sentence(escape_untrusted(value))[:limit]


def validate_item(
    raw: Mapping[str, Any],
    *,
    alerts_by_id: Mapping[str, OverlapAlert],
    allowed_texts: Iterable[str],
) -> tuple[DifferentiationItem | None, str | None]:
    """LLM 항목 하나 → (검증된 항목, None) 또는 (None, 폐기 사유)."""
    doc_id = normalize_evidence_id(str(raw.get("doc_id", "")))
    alert = alerts_by_id.get(doc_id)
    if alert is None:
        return None, DISCARD_UNKNOWN_DOC
    overlap_summary = _text(raw.get("overlap_summary"))
    build_on = _text(raw.get("build_on"))
    directions_raw = raw.get("differentiation")
    if isinstance(directions_raw, str):
        directions_raw = [directions_raw]
    directions = [t for t in (_text(d) for d in (directions_raw or []) if isinstance(d, str)) if t]
    directions = list(dict.fromkeys(directions))[:MAX_DIRECTIONS]
    if not directions or not overlap_summary:
        return None, DISCARD_NO_DIRECTION
    evidence_raw = raw.get("evidence")
    evidence = [
        normalize_evidence_id(str(e)) for e in (evidence_raw or []) if isinstance(e, str)
    ] or [doc_id]
    evidence = list(dict.fromkeys(e for e in evidence if e))
    if any(e not in alerts_by_id for e in evidence):
        return None, DISCARD_EVIDENCE
    texts = [overlap_summary, build_on, *directions]
    if any(has_foreign_script(t) for t in texts):
        return None, DISCARD_FOREIGN
    allowed = list(allowed_texts)
    if any(ungrounded(t, allowed) for t in texts):
        return None, DISCARD_UNGROUNDED
    return (
        DifferentiationItem(
            doc_id=doc_id,
            title=alert.title,
            tier=alert.tier,
            status=alert.status,
            overlap_summary=overlap_summary,
            build_on=build_on,
            differentiation=directions,
            evidence=evidence,
        ),
        None,
    )
