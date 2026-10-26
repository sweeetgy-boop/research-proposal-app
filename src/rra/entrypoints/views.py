"""진입점 공용 직렬화. RunManager.DraftView → 출력용 dict (CLI·MCP 가 같은 모양을 쓴다).

현행 근거 규칙: 근거 필수 섹션 밖에서는 제안자 입력만으로 쓴 문장이 허용된다.
그런 문장은 evidence 가 비어 있고 source="proposer_input" 으로 구분해 보여 준다.
앱이 규칙으로 만든 확정 문장(유사과제 없음 등)은 source="app".

선택형 섹션(과제유형·활용계획·전략)은 choices 에 LLM 제안(proposed)과 사용자 확정(confirmed)을
따로 싣는다. 확정 전이면 confirmed 는 null.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _same(text: str) -> str:
    return text


def _source(sent: Any) -> str:
    if sent.origin == "app":
        return "app"
    return "retrieved" if sent.evidence else "proposer_input"


def _choices(sec: Any, view: Any) -> dict[str, Any] | None:
    options = view.choice_options.get(sec.key)
    if options is None:
        return None
    confirmed = view.confirmation.choices.get(sec.key) if view.confirmation else None

    def labelled(ids: list[str]) -> list[dict[str, str]]:
        return [{"id": i, "label": options.get(i, i)} for i in ids]

    return {
        "proposed": labelled(sec.choices),
        "confirmed": labelled(confirmed) if confirmed is not None else None,
        "options": labelled(list(options)),
    }


def draft_payload(view: Any, *, clean: Callable[[str], str] = _same) -> dict[str, Any]:
    """clean: 비신뢰 텍스트(초안 문장·문서 제목·lint 메시지)에 적용할 정리 함수."""
    state = view.state
    return {
        "run_id": state.run_id,
        "status": state.status,
        "template": state.template,
        "legacy": view.legacy,
        "progress": list(state.progress),
        "steps": [
            {
                "name": s.name,
                "status": s.status,
                "error": s.error,
                "sentences": s.sentences,
                "dropped": s.dropped,
                "parse": s.parse,
                "raw_chars": s.raw_chars,
            }
            for s in state.steps
        ],
        "sections": [
            {
                "key": sec.key,
                "sentences": [
                    {
                        "text": clean(sent.text),
                        "evidence": sent.evidence,
                        "source": _source(sent),
                    }
                    for sent in sec.sentences
                ],
                "choices": _choices(sec, view),
            }
            for sec in view.sections
        ],
        "citations": [
            {"id": c.id, "doc_id": c.doc_id, "title": clean(c.title) if c.title else None}
            for c in view.citations
        ],
        "problems": [
            {
                "section": p["section"],
                "code": p["code"],
                "severity": p.get("severity", "error"),
                "message": clean(p["message"]),
                "sentence": p.get("sentence"),
            }
            for p in state.problems
        ],
    }


# 한 줄 칸 slot → 양식 칸 이름 (render_check 출력용). 섹션 키는 rules.yaml titles 로 푼다.
SLOT_LABELS = {
    "title": "1-가 연구과제명",
    "budget.account": "1-나 예산과목",
    "budget.amount_thousand_krw": "1-나 금액",
    "strategy_alignment:task": "2-가-(3) 전략과제",
    "department": "제안부서",
    "proposed_on": "제안일자",
    "proposer.rank": "제안자 직급",
    "proposer.name": "제안자 성명",
    "proposer.phone": "제안자 연락처",
    "head.rank": "부서장 직급",
    "head.name": "부서장 성명",
    "head.phone": "부서장 연락처",
}


def render_check_payload(
    check: Any, *, titles: dict[str, str] | None = None, clean: Callable[[str], str] = _same
) -> dict[str, Any]:
    """RenderCheck → dict (CLI·UI·REST 공용). 렌더를 막지 않는 알림 목록이다."""
    names = {**SLOT_LABELS, **(titles or {})}
    return {
        "count": check.count,
        "unresolved": [
            {
                "section": p.section,
                "code": p.code,
                "severity": p.severity,
                "message": clean(p.message),
                "sentence": p.sentence,
            }
            for p in check.unresolved
        ],
        "overflow": [
            {
                "slot": o.slot,
                "label": names.get(o.slot, o.slot),
                "chars": o.chars,
                "limit": o.limit,
                "kind": o.kind,
            }
            for o in check.overflow
        ],
        "notes": list(check.notes),
    }


def render_check_lines(payload: dict[str, Any]) -> list[str]:
    """render_check_payload → 사람이 읽는 줄 (CLI stdout·UI 캡션). 비면 빈 목록."""
    if not payload["count"]:
        return []
    lines = [f"렌더 전 점검: 알림 {payload['count']}건 (렌더는 진행합니다)"]
    for p in payload["unresolved"]:
        where = p["section"] + (f" 문장 {p['sentence'] + 1}" if p["sentence"] is not None else "")
        lines.append(f" - [{p['severity']}] {where}: {p['message']}")
    for o in payload["overflow"]:
        kind = "한 줄 칸" if o["kind"] == "line" else "본문 상한"
        lines.append(f" - 칸 길이 초과({kind}): {o['label']} {o['chars']}자 > {o['limit']}자")
    lines.extend(f" - {n}" for n in payload["notes"])
    return lines


def alerts_payload(alerts: list[Any], *, clean: Callable[[str], str] = _same) -> dict[str, Any]:
    """유사과제 경보 목록 → 출력용 dict (MCP·REST 공용). 제목은 수집 문서에서 온 비신뢰 텍스트."""
    return {
        "blocking": any(a.blocking for a in alerts),
        "alerts": [
            {
                "doc_id": a.doc_id,
                "title": clean(a.title),
                "tier": a.tier,
                "similarity": round(a.similarity, 4),
                "blocking": a.blocking,
                "basis": a.basis,
                "keywords": list(a.keywords),
            }
            for a in alerts
        ],
    }


def run_state_payload(state: Any, *, legacy: bool = False) -> dict[str, Any]:
    """RunState → 상태 조회 응답 (초안 본문 없음)."""
    done, total = state.progress
    return {
        "run_id": state.run_id,
        "status": state.status,
        "progress": [done, total],
        "template": state.template,
        "legacy": legacy,
        "created_at": state.created_at,
        "updated_at": state.updated_at,
        "steps": [{"name": s.name, "status": s.status, "error": s.error} for s in state.steps],
    }


def chunks_payload(
    chunks: list[Any], *, clean: Callable[[str], str] = _same
) -> list[dict[str, Any]]:
    """검색 결과 청크 → dict. 전부 비신뢰(trust=untrusted) — 지시가 아니라 자료다."""
    return [
        {
            "chunk_id": c.chunk_id,
            "doc_id": c.doc_id,
            "ordinal": c.ordinal,
            "basis": c.basis,
            "text": clean(c.text),
            "trust": "untrusted",
        }
        for c in chunks
    ]
