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
            }
            for p in state.problems
        ],
    }
