from __future__ import annotations

from pydantic import BaseModel, Field

from .request import ProposalRequest


class Sentence(BaseModel):
    text: str
    evidence: list[str] = Field(default_factory=list)  # doc_id 또는 chunk_id


class Section(BaseModel):
    key: str  # slots.yaml 키와 일치
    sentences: list[Sentence]

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.sentences)


class Draft(BaseModel):
    run_id: str
    request: ProposalRequest
    sections: list[Section]
    retrieved_ids: set[str] = Field(default_factory=set)  # A: 이번 run 검색 집합

    def section(self, key: str) -> Section | None:
        return next((s for s in self.sections if s.key == key), None)
