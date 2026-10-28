"""작성·편집 AI 결과의 공용 직렬화 (REST·MCP 공용, 2026-10-28 레인 B). 로직 없음.

LLM 이 쓴 글(작성안 문장·질문)과 수집 자료 인용은 비신뢰 — clean 으로 정리해 내보낸다.
사유 코드는 한국어 라벨을 함께 준다(화면은 코드를 보이지 않는다).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rra.application.usecases.argon_first import reason_label


def _same(text: str) -> str:
    return text


POLICY_STATUS_LABELS = {
    "ok": "작성안",
    "empty": "해당 없음 — 아이디어와 관련된 정책 자료 구간을 찾지 못했습니다",
    "filtered": "규칙에 걸러짐 — 근거·정책명·수치 검사를 통과한 문장이 없습니다",
    "failed": "호출 실패",
}


def _source(s: Any, clean: Callable[[str], str]) -> dict[str, Any]:
    return {
        "chunk_id": s.chunk_id,
        "doc_id": s.doc_id,
        "source": s.source,
        "source_label": s.source_label,
        "title": clean(s.title),
        "year": s.year,
        "page": clean(s.page) if s.page else None,
        "quote": clean(s.quote),
        "url": s.url,
        "trust": "untrusted",
    }


def _sentences(items: Any, clean: Callable[[str], str]) -> list[dict[str, Any]]:
    return [{"text": clean(x.text), "evidence": list(x.evidence)} for x in items]


def policy_cards_payload(result: Any, *, clean: Callable[[str], str] = _same) -> dict[str, Any]:
    """PolicyCardsResult → dict. cards 는 그대로 RunIn.policy_choice(mode card) 로 되돌려
    보낼 수 있다."""
    return {
        "cards": [
            {
                "id": c.id,
                "direction": c.direction,
                "direction_label": c.direction_label,
                "sentences": _sentences(c.sentences, clean),
                "sources": [_source(s, clean) for s in c.sources],
            }
            for c in result.cards
        ],
        "count": len(result.cards),
        "status": result.status,
        "status_label": POLICY_STATUS_LABELS.get(result.status, result.status),
        "reason": result.reason,
        "reason_label": reason_label(result.reason),
        "passages": result.passages,
        "dropped": result.dropped,
        "excluded_docs": list(result.excluded_docs),
        "transfer": dict(result.record),
    }


def policy_polish_payload(result: Any, *, clean: Callable[[str], str] = _same) -> dict[str, Any]:
    choice = result.choice
    return {
        "choice": None
        if choice is None
        else {
            "mode": choice.mode,
            "card_ids": list(choice.card_ids),
            "sentences": _sentences(choice.sentences, clean),
            "sources": [_source(s, clean) for s in choice.sources],
        },
        "reason": result.reason,
        "reason_label": reason_label(result.reason),
        "dropped": result.dropped,
        "transfer": dict(result.record),
    }


def change_summary_payload(summary: Any) -> dict[str, Any]:
    return summary.dump()


REWRITE_REASON_LABELS = {
    "policy_basis_needed": "정책 근거가 없어 쓸 수 없습니다 — 정책적 중요도 작성안에서 고르십시오",
    "input_missing": "근거가 될 제안자 입력이 없습니다",
    "catalog_empty": "선택지 목록이 비어 있습니다",
    "no_relevant_evidence": "해당 없음 — 관련도 하한을 넘는 근거 자료가 없습니다",
    "app_section": "해당 없음 — 앱이 유사과제 판정으로 쓰는 섹션입니다",
}


def rewrite_reason_label(code: str | None) -> str | None:
    if code is None:
        return None
    return REWRITE_REASON_LABELS.get(code) or reason_label(code)


def clarify_payload(result: Any, *, clean: Callable[[str], str] = _same) -> dict[str, Any]:
    """ClarifyResult → dict. questions 는 {id, question, topic, topic_label, hint}."""
    out = result.dump()
    out["questions"] = [{**q, "question": clean(q["question"])} for q in out["questions"]]
    return out


def clarify_off_payload() -> dict[str, Any]:
    return {
        "questions": [],
        "status": "off",
        "status_label": "보강 질문이 꺼져 있습니다",
        "reason": "off",
        "reason_label": reason_label("off"),
        "source": "none",
        "policy_needed": False,
        "transfer": {},
    }
