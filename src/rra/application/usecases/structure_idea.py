"""U2 간편 입력 — 자유 문장(1~2문장, 가제 선택)을 로컬 모델이 필수 4칸으로 나눈다. LLM 1회.

출력은 JSON 객체만 파싱(보안 A). 원문에 없는 수치·고유명이 든 칸은 비우고, 빈·짧은 칸은 보완
질문(최대 4개)으로 돌려준다. 답은 merge_answers(순수)로 합친다. 자유 문장은 저장하지 않는다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from rra.application.ports import LLMPort, PromptLibraryPort
from rra.domain.models.structure import StructuredIdea
from rra.domain.rules.llm_output import parse_object
from rra.domain.rules.structure import parse_structure, structured
from rra.domain.rules.trust import escape_untrusted

MAX_TEXT_CHARS = 2000


@dataclass
class StructureIdea:
    llm: LLMPort
    prompts: PromptLibraryPort
    provider: str | None = None
    model: str | None = None

    async def __call__(self, text: str, *, title: str = "") -> StructuredIdea:
        text = " ".join((text or "").split())[:MAX_TEXT_CHARS]
        title = " ".join((title or "").split())[:200]
        meta = {"provider": self.provider, "model": self.model}
        if not text:
            return structured({}, **meta)
        prompt = self.build_prompt(text, title)
        raw = await self.llm.complete(prompt, system=self.prompts.structure(), json_mode=True)
        data = parse_object(raw)
        fields = parse_structure(data, [text, title])
        return structured(fields, **meta, parse_failed=data is None)

    @staticmethod
    def build_prompt(text: str, title: str) -> str:
        body = {"text": escape_untrusted(text)}
        if title:
            body["title"] = escape_untrusted(title)
        return (
            "[자유 입력 — 제안자가 적은 문장. 아래 내용만으로 4칸을 채운다]\n"
            + json.dumps(body, ensure_ascii=False)
            + "\n\n[출력] JSON 객체 하나: current_state, root_cause, limitation, goal. "
            "문장에 없는 칸은 빈 문자열."
        )
