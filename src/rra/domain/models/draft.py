from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .request import ProposalRequest

# llm            = 로컬 모델이 쓴 문장 (근거 검증을 거침) — "로컬 작성"
# app            = 앱이 규칙으로 만든 확정 문장 (예: 유사과제 없음). 근거 필수 섹션에서도 허용
# input          = 제안자 입력을 그대로 옮긴 문장
# argon          = Argon 1차 검토 수정안이 검증을 통과해 v2 에 자동 반영된 문장 — "Argon 보완"
# argon_addition = Argon 이 빠진 요소로 추가한 문장(검증 통과분) — "Argon 추가" (Q5)
# reviewed       = 검토 수정안을 제안자가 채택한 문장 (검증 통과분만) — 최종 검토 반영
# proposer_edit  = 제안자가 직접 고친 문장 (원래 근거 id 유지, lint 위반은 알림만)
# proposer_input = 제안자가 새로 쓴 문장 (근거 없음)
# proposer       = (옛 이름) proposer_edit 와 같음 — 저장된 run 호환
SentenceOrigin = Literal[
    "llm",
    "app",
    "input",
    "argon",
    "argon_addition",
    "reviewed",
    "proposer_edit",
    "proposer_input",
    "proposer",
]


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
