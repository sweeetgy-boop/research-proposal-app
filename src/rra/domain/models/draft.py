from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .request import ProposalRequest

# llm   = LLM 이 쓴 문장 (근거 검증을 거침)
# app   = 앱이 규칙으로 만든 확정 문장 (예: 유사과제 없음). 근거 필수 섹션에서도 근거 없이 허용
# input = 제안자 입력을 그대로 옮긴 문장
SentenceOrigin = Literal["llm", "app", "input"]


class Sentence(BaseModel):
    text: str
    evidence: list[str] = Field(default_factory=list)  # doc_id 또는 chunk_id
    origin: SentenceOrigin = "llm"


class Section(BaseModel):
    key: str  # rules.yaml sections 키와 일치
    sentences: list[Sentence]
    # 선택형 섹션만: LLM 이 제안한 선택지 id (허용 목록 검증을 통과한 것만). 확정은 사용자가 한다.
    choices: list[str] = Field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.sentences)


class Draft(BaseModel):
    run_id: str
    request: ProposalRequest
    sections: list[Section]
    retrieved_ids: set[str] = Field(default_factory=set)  # A: 이번 run 검색 집합
    template: str | None = None

    def section(self, key: str) -> Section | None:
        return next((s for s in self.sections if s.key == key), None)
