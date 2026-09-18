"""진입점 공용 직렬화. RunManager.DraftView → 출력용 dict (CLI·MCP 가 같은 모양을 쓴다).

현행 근거 규칙: 근거 필수 섹션 밖에서는 제안자 입력만으로 쓴 문장이 허용된다.
그런 문장은 evidence 가 비어 있고 source="proposer_input" 으로 구분해 보여 준다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _same(text: str) -> str:
    return text


def draft_payload(view: Any, *, clean: Callable[[str], str] = _same) -> dict[str, Any]:
    """clean: 비신뢰 텍스트(초안 문장·문서 제목·lint 메시지)에 적용할 정리 함수."""
    state = view.state
    return {
        "run_id": state.run_id,
        "status": state.status,
        "progress": list(state.progress),
        "steps": [
            {
                "name": s.name,
                "status": s.status,
                "error": s.error,
                "sentences": s.sentences,
                "dropped": s.dropped,
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
                        "source": "retrieved" if sent.evidence else "proposer_input",
                    }
                    for sent in sec.sentences
                ],
            }
            for sec in view.sections
        ],
        "citations": [
            {"id": c.id, "doc_id": c.doc_id, "title": clean(c.title) if c.title else None}
            for c in view.citations
        ],
        "problems": [
            {"section": p["section"], "code": p["code"], "message": clean(p["message"])}
            for p in state.problems
        ],
    }
