"""공고문 대조 결과 (P2-7, #13 선행 훅). LLM 없음 — 저장소 검색 유사도만."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

MAX_NOTICE_MATCHES = 3


class NoticeMatch(BaseModel):
    """접수 중인 공고 1건 — 제안자에게 보여 줄 목록 항목. 제안서에 자동으로 들어가지 않는다."""

    doc_id: str
    title: str
    agency: str | None = None
    program: str | None = None
    posted: date | None = None
    deadline: date | None = None  # 접수 마감일 (= Document.valid_until)
    days_left: int | None = None
    url: str | None = None
    similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    trust: str = "untrusted"
