"""정책 근거 추천 — ① 입력 뒤 정책(policy) 문서에서 고른 문구 3~5개.

제안자가 고른 것만 policy_basis 로 들어간다."""

from __future__ import annotations

from pydantic import BaseModel, Field

MAX_QUOTE = 300
MAX_SUGGESTIONS = 5
MIN_SUGGESTIONS = 3


class PolicySuggestion(BaseModel):
    """정책 문서의 문구 하나. quote 는 문서에 있는 그대로(비신뢰 텍스트)."""

    doc_id: str
    title: str = Field(max_length=300)
    year: int | None = None
    page: str | None = Field(default=None, max_length=120)  # 표·장 제목 또는 쪽 — 모르면 None
    quote: str = Field(max_length=MAX_QUOTE)
    url: str | None = None
    menu_path: str | None = Field(default=None, max_length=200)
    keywords: list[str] = Field(default_factory=list)  # 질의와 겹친 키워드
    similarity: float | None = None
