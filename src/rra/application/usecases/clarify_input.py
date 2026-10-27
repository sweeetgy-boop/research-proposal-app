"""Q1 입력 보강 질문 — 초안 생성 전에 로컬 모델이 필수 4칸을 점검해 빠진 정보를 최대 3개 질문으로.

출력(JSON 만 파싱): {"questions": ["…", …]} — 이미 충분하면 빈 배열. 질문은 한국어 문장, 200자
이내, 한자·가나 없음. 답은 ProposalRequest.supplement("보충 정보")로 저장되어 설계도·작성
프롬프트에 들어간다(제안자 입력 근거로 취급). 건너뛸 수 있다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from rra.application.ports import LLMPort, PromptLibraryPort
from rra.domain.models import ProposalRequest
from rra.domain.rules.foreign_script import has_foreign_script
from rra.domain.rules.llm_output import clean_sentence, parse_object
from rra.domain.rules.trust import escape_untrusted

MAX_QUESTIONS = 3
MAX_QUESTION_CHARS = 200


def validate_questions(data: object, limit: int = MAX_QUESTIONS) -> list[str]:
    """LLM 출력 → 질문 목록(비신뢰 텍스트 정리, 중복·외국 문자·빈 문자열 제거, 상한)."""
    if not isinstance(data, dict):
        return []
    raw = data.get("questions")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for q in raw:
        if not isinstance(q, str):
            continue
        text = clean_sentence(escape_untrusted(q))[:MAX_QUESTION_CHARS]
        if not text or has_foreign_script(text) or text in out:
            continue
        out.append(text)
        if len(out) >= limit:
            break
    return out


@dataclass
class ClarifyInput:
    llm: LLMPort
    prompts: PromptLibraryPort
    max_questions: int = MAX_QUESTIONS

    async def __call__(self, req: ProposalRequest) -> list[str]:
        prompt = "\n\n".join(
            [
                "[제안 입력]\n" + json.dumps(req.prompt_view(), ensure_ascii=False),
                f'[출력] JSON 객체 하나: {{"questions": [최대 {self.max_questions}개]}}. '
                "이미 충분하면 빈 배열.",
            ]
        )
        raw = await self.llm.complete(prompt, system=self.prompts.clarify(), json_mode=True)
        return validate_questions(parse_object(raw), self.max_questions)


def apply_answers(
    req: ProposalRequest, answers: dict[str, str] | list[tuple[str, str]]
) -> ProposalRequest:
    """답을 보충 정보로 — "질문: 답" 줄을 supplement 에 덧붙인다 (비면 그대로)."""
    pairs = list(answers.items()) if isinstance(answers, dict) else list(answers)
    lines = [
        f"{clean_sentence(q)[:MAX_QUESTION_CHARS]}: {clean_sentence(a)}"
        for q, a in pairs
        if isinstance(a, str) and clean_sentence(a)
    ]
    if not lines:
        return req
    existing = req.supplement.strip()
    joined = "\n".join(([existing] if existing else []) + lines)
    return req.model_copy(update={"supplement": joined})
