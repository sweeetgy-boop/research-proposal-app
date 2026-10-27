"""Q2 섹션 설계도 — 섹션 작성 전에 로컬 모델이 만드는 섹션별 {핵심 메시지, 쓸 근거 id, 연결}.

runs/<run_id>/outline.json 에 저장되고, 각 섹션 프롬프트에 그 섹션 설계와 전체 설계 요약으로
들어간다. 검증(domain/rules/outline.validate_outline): doc_id 는 검색 결과 안, 섹션 키는 양식 안.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

MAX_MESSAGE_CHARS = 400


class SectionPlan(BaseModel):
    key: str
    message: str = Field(default="", max_length=MAX_MESSAGE_CHARS)  # 핵심 메시지 1~2문장
    evidence: list[str] = Field(default_factory=list)  # 쓸 근거 doc_id/chunk_id (검색 결과 안)
    links: list[str] = Field(default_factory=list)  # 연결되는 다른 섹션 키


class Outline(BaseModel):
    sections: list[SectionPlan] = Field(default_factory=list)
    summary: str = Field(default="", max_length=MAX_MESSAGE_CHARS * 2)  # 전체 설계 요약(앱이 합침)
    discarded: list[dict[str, str]] = Field(default_factory=list)  # {key, reason}
    retries: int = 0
    created_at: str | None = None

    def plan(self, key: str) -> SectionPlan | None:
        return next((s for s in self.sections if s.key == key), None)

    def summary_text(self) -> str:
        if self.summary:
            return self.summary
        return " / ".join(f"{s.key}: {s.message}" for s in self.sections if s.message)
