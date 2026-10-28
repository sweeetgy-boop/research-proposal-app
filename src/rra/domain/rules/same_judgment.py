"""② AI 같음 판정의 순수 규칙 (2026-10-28 레인 A).

상위 후보(최대 10건)를 한 번의 LLM 호출로 "대상·문제·방법이 실제로 같은가" 판정한다. 출력은 JSON
객체 하나 {"items": [{doc_id, verdict, reason}]} 만 받는다 (보안 A: LLM 출력은 비신뢰 — doc_id 는
보낸
후보 안에서만, 이유는 구획 태그 무력화·한 줄 상한·한자/가나 제거).

- same(같다) 만 차단. partial(일부 겹침)·different(다르다) 는 차단하지 않는다.
- 모델이 빠뜨린 후보는 규칙 판정 그대로(judged_by=rule, 이유 "AI 판정 없음 — 규칙 기준").
- AI 가 모두 실패하면 규칙 판정 그대로(judged_by=rule) — 화면은 "AI 판정 실패 — 규칙 기준"과
  [다시 시도] 를 보인다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from rra.domain.models import OverlapAlert
from rra.domain.rules.foreign_script import has_foreign_script
from rra.domain.rules.llm_output import clean_sentence
from rra.domain.rules.trust import escape_untrusted, normalize_evidence_id

MAX_JUDGE = 10
MAX_REASON_CHARS = 120
NO_VERDICT_REASON = "AI 판정 없음 — 규칙 기준"
FAILED_MESSAGE = "AI 판정 실패 — 규칙 기준"
_VERDICTS: dict[str, str] = {
    "same": "same",
    "같다": "same",
    "같음": "same",
    "동일": "same",
    "partial": "partial",
    "일부": "partial",
    "일부 겹침": "partial",
    "different": "different",
    "다르다": "different",
    "다름": "different",
}
VERDICT_LABELS: dict[str, str] = {"same": "같다", "partial": "일부 겹침", "different": "다르다"}


def pick_for_judgment(alerts: Sequence[OverlapAlert], limit: int = MAX_JUDGE) -> list[str]:
    """판정에 보낼 doc_id — reranker 점수(없으면 e5 유사도) 높은 순 상위 limit 건."""
    ranked = sorted(
        alerts,
        key=lambda a: (
            -(a.rerank_score if a.rerank_score is not None else -1.0),
            -a.similarity,
            a.doc_id,
        ),
    )
    return [a.doc_id for a in ranked[:limit]]


def clean_reason(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = clean_sentence(escape_untrusted(value)).replace("\n", " ").strip()
    if has_foreign_script(text):
        return ""
    if len(text) > MAX_REASON_CHARS:
        text = text[: MAX_REASON_CHARS - 1].rstrip() + "…"
    return text


def parse_verdicts(
    data: Mapping[str, Any] | None, allowed_ids: Sequence[str]
) -> dict[str, tuple[str, str]] | None:
    """LLM JSON → {doc_id: (verdict, 이유)}. 형식이 틀리면 None(실패로 본다). 후보 밖 doc_id·모르는
    판정 값은 버린다. 하나도 못 읽으면 None."""
    if not isinstance(data, Mapping):
        return None
    items = data.get("items")
    if not isinstance(items, list):
        return None
    allowed = set(allowed_ids)
    out: dict[str, tuple[str, str]] = {}
    for raw in items[: len(allowed) * 2]:
        if not isinstance(raw, Mapping):
            continue
        doc_id = normalize_evidence_id(str(raw.get("doc_id", "")))
        verdict = _VERDICTS.get(str(raw.get("verdict", "")).strip().lower())
        if doc_id not in allowed or verdict is None or doc_id in out:
            continue
        out[doc_id] = (verdict, clean_reason(raw.get("reason")))
    return out or None


def apply_verdicts(
    alerts: Sequence[OverlapAlert],
    verdicts: Mapping[str, tuple[str, str]],
    judged_ids: Sequence[str],
    judged_by: str,
) -> list[OverlapAlert]:
    """판정을 행에 붙인다. 판정한 행: same 만 차단. 보낸 후보인데 빠진 행: 규칙 판정 그대로.
    보내지 않은 행(상위 밖): 차단하지 않는다 — AI 가 본 상위 후보보다 낮은 순위다."""
    sent = set(judged_ids)
    out: list[OverlapAlert] = []
    for a in alerts:
        rule = a.rule_blocking if a.rule_blocking is not None else a.blocking
        if a.doc_id in verdicts:
            verdict, reason = verdicts[a.doc_id]
            out.append(
                a.model_copy(
                    update={
                        "judgment": verdict,
                        "judgment_reason": reason,
                        "judged_by": judged_by,
                        "blocking": verdict == "same",
                        "rule_blocking": rule,
                    }
                )
            )
        elif a.doc_id in sent:
            out.append(
                a.model_copy(
                    update={
                        "judged_by": "rule",
                        "judgment_reason": NO_VERDICT_REASON,
                        "blocking": rule,
                        "rule_blocking": rule,
                    }
                )
            )
        else:
            out.append(a.model_copy(update={"blocking": False, "rule_blocking": rule}))
    return _blocking_first(out)


def rule_fallback(alerts: Sequence[OverlapAlert]) -> list[OverlapAlert]:
    """AI 판정 실패 — 규칙 판정 그대로, 행마다 judged_by=rule."""
    out = []
    for a in alerts:
        rule = a.rule_blocking if a.rule_blocking is not None else a.blocking
        out.append(
            a.model_copy(
                update={
                    "judged_by": "rule",
                    "judgment": None,
                    "judgment_reason": "",
                    "blocking": rule,
                    "rule_blocking": rule,
                }
            )
        )
    return _blocking_first(out)


def _blocking_first(alerts: list[OverlapAlert]) -> list[OverlapAlert]:
    return sorted(alerts, key=lambda a: -int(a.blocking))  # 안정 정렬 — 입력(reranker) 순서 유지
