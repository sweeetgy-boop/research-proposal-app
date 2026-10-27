from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

SourceType = Literal[
    "openalex", "scienceon", "kipris_kr", "kipris_intl", "ntis", "alio", "own", "korail_web"
]
# policy=공사 경영목표·전략·ESG·정책 자료(정책적 중요도·경영전략 정합성 근거),
# korail_news=보도자료(특이사항·현황 보조). 둘 다 기술적 중요도 근거·유사과제 판정에는 쓰지 않는다
# (domain/rules/retrieval_scope.py).
DocType = Literal["paper", "patent", "internal_report", "rnd_project", "policy", "korail_news"]
# 본문의 근거. full_text=원문 파일, summary=공개 요약(원문 비공개), abstract=초록·과제요약
TextBasis = Literal["full_text", "summary", "abstract"]
# public=외부(검토 LLM 등)로 보낼 수 있음, internal=사내 전용(외부 전송 제외·구획 표시)
Visibility = Literal["public", "internal"]


class Document(BaseModel):
    """수집 문서. A: body/abstract 는 항상 비신뢰 데이터."""

    doc_id: str  # f"{source}:{native_id}"
    source: SourceType
    doc_type: DocType
    title: str
    abstract: str | None = None
    body: str | None = None
    pub_date: date | None = None
    orgs: list[str] = Field(default_factory=list)  # korail / krri / kr / 외부
    authors: list[str] = Field(default_factory=list)
    codes: list[str] = Field(default_factory=list)  # IPC/CPC 등
    lang: str = "ko"
    url: str | None = None
    doi: str | None = None
    application_no: str | None = None  # 특허 출원번호
    department: str | None = None  # 철도연구원 등
    project_period: tuple[date, date] | None = None
    toc: list[str] | None = None
    text_basis: TextBasis = "full_text"
    valid_until: date | None = None  # 이 날짜(포함)까지만 검색·precheck 대상. None=만료 없음
    visibility: Visibility = "public"
    raw: dict[str, Any] = Field(default_factory=dict)
    trust: Literal["untrusted"] = "untrusted"

    def is_valid_on(self, day: date) -> bool:
        return self.valid_until is None or self.valid_until >= day


class Chunk(BaseModel):
    chunk_id: str  # f"{doc_id}#{n}"
    doc_id: str
    ordinal: int
    heading: str | None = None
    text: str
    basis: TextBasis | None = None  # None: basis 도입 전 스냅샷
    visibility: Visibility | None = None  # None: 도입 전 스냅샷 (public 으로 본다)
    # 검색 결과에서만: 질의와의 코사인 [0,1]. 벡터 색인이 없거나 적재용 청크면 None
    similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    trust: Literal["untrusted"] = "untrusted"
