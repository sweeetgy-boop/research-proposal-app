from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .document import TextBasis

Tier = Literal["own", "national_rnd", "domestic_rail", "external", "procurement"]
# 사내(철도연구원·공사 과제 기록) / 국가R&D 과제(NTIS 과제검색, 수행기관 무관) / 공단 등 /
# KRRI·외부 / 발주 용역 공고(P2-6, doc_type procurement)
# own 티어의 세부 구분 — institute: 철도연구원 부서, company: 그 외 공사 부서(사내 과제 기록 출처)
OwnDetail = Literal["institute", "company"]
SameVerdict = Literal["same", "partial", "different"]
JudgedBy = Literal["argon", "local", "rule"]
SimilarChoiceValue = Literal["similar", "unrelated"]


class OverlapAlert(BaseModel):
    doc_id: str
    title: str
    tier: Tier
    similarity: float
    blocking: bool  # 임계치 초과(+ 키워드 조건) → 제안 진행 전 확인 필요
    basis: TextBasis | None = None  # summary 면 공개 요약만으로 판정한 것
    keywords: list[str] = Field(default_factory=list)  # 질의와 문서가 공유한 키워드 (일반어 제외)
    # 사내 과제 기록의 상태 (completed·ongoing·stopped·rejected·proposed), 발주 용역 공고는
    # procuring
    # ("용역으로 진행 중/예정"). 수집 문서 raw.status 에서
    status: str | None = None
    own_detail: OwnDetail | None = (
        None  # tier=own 일 때: 철도연구원 부서(institute) / 그 외 공사 부서(company)
    )
    # ── ② 판정 정확도 (2026-10-28 레인 A, ADR "precheck 판정") ──
    # reranker(cross-encoder) 점수 0~1 — 있으면 차단 판단의 주 점수(e5 유사도는 후보 검색용)
    rerank_score: float | None = None
    rule_blocking: bool | None = None  # 규칙(점수 + 핵심 키워드) 판정 — AI 판정 전 값
    # AI 판정(대상·문제·방법이 실제로 같은가): same(같다 → 차단) | partial(일부 겹침) | different
    judgment: SameVerdict | None = None
    judgment_reason: str = ""  # 한 줄 이유 (LLM 출력 — 비신뢰, 정리 뒤)
    judged_by: JudgedBy | None = None  # argon | local | rule(AI 실패·미판정 → 규칙 기준)
    merged_ids: list[str] = Field(
        default_factory=list
    )  # 제목이 같은 다른 문서(NTIS 번호만 다른 중복)
    choice: SimilarChoiceValue | None = None  # 제안자 선택 [유사함]=similar / [관련 없음]=unrelated


class RelatedResearch(BaseModel):
    """② 유사과제 확인의 "관련 연구"(참고) 한 건 — 논문·보고서·특허. 판정·차단에 쓰지 않는다
    (ADR 0028)."""

    doc_id: str
    title: str  # 비신뢰 텍스트 (수집 문서 제목)
    source: str
    doc_type: str
    year: int | None = None
    similarity: float
    url: str | None = None


JudgmentStatus = Literal["ai", "rule_fallback", "off", "no_candidates"]


class JudgmentInfo(BaseModel):
    """② AI 같음 판정의 요약 — 화면 안내와 [다시 시도] 용. 실패 사유는 예외 클래스명만(본문
    없음)."""

    status: JudgmentStatus = "off"
    judged_by: JudgedBy | None = None
    provider: str | None = None
    model: str | None = None
    candidates: int = 0  # 판정에 보낸 후보 수 (최대 10)
    calls: int = 0  # 외부 LLM 호출 수
    errors: list[str] = Field(default_factory=list)  # 단계별 실패 사유 코드 (argon:timeout 등)
    excluded_doc_ids: list[str] = Field(default_factory=list)  # 외부 전송에서 뺀 internal 문서


class PrecheckResult(BaseModel):
    """② precheck 결과 — 판정 알림(과제형 자료원만) + 관련 연구 목록(참고)."""

    alerts: list[OverlapAlert] = Field(default_factory=list)
    related_research: list[RelatedResearch] = Field(default_factory=list)
    judgment: JudgmentInfo = Field(default_factory=JudgmentInfo)
    core_keywords: list[str] = Field(default_factory=list)  # 공유 키워드 판정에 쓴 아이디어 핵심어
    keyword_origin: str = "rule"  # argon | local | rule

    @property
    def blocking(self) -> bool:
        return any(a.blocking for a in self.alerts)


MAX_DIRECTIONS = 3
MAX_ITEM_CHARS = 600


class DifferentiationItem(BaseModel):
    """겹친 과제 하나에 대한 활용·차별화 제안 (LLM 출력을 검증한 뒤의 값)."""

    doc_id: str
    title: str  # 비신뢰 텍스트 (수집 문서 제목)
    tier: Tier
    status: str | None = None  # 사내 기록의 상태. rejected 면 "보완 재제안" 관점
    overlap_summary: str = Field(max_length=MAX_ITEM_CHARS)  # 무엇이 겹치는지
    build_on: str = Field(max_length=MAX_ITEM_CHARS)  # 그 과제 결과를 이어받을 점
    differentiation: list[str] = Field(min_length=1, max_length=MAX_DIRECTIONS)  # 차별화 방향
    evidence: list[str] = Field(default_factory=list)  # 겹친 과제 doc_id


class DifferentiationProposal(BaseModel):
    """유사과제 활용·차별화 제안 결과 + 외부 전송 범위 (manifest 용. 본문은 run 에 안 남긴다)."""

    items: list[DifferentiationItem] = Field(default_factory=list)
    discarded: list[dict[str, str]] = Field(default_factory=list)  # {doc_id, reason}
    provider: str | None = None
    model: str | None = None
    fallback_local: bool = False  # differentiate 단계 키가 없어 로컬(compose) 모델로 돌림
    public_doc_ids: list[str] = Field(default_factory=list)
    internal_doc_ids: list[str] = Field(default_factory=list)
    excluded_doc_ids: list[str] = Field(default_factory=list)  # include_internal=false 로 뺀 것
    calls: int = 0
    skipped_reason: str | None = None  # no_candidates | no_documents | parse_failed

    def transfer(self) -> dict[str, object]:
        """manifest 에 남기는 전송 기록 (검토 단계의 ReviewTransfer 와 같은 범위)."""
        return {
            "provider": self.provider,
            "model": self.model,
            "fallback_local": self.fallback_local,
            "public_doc_ids": list(self.public_doc_ids),
            "internal_doc_ids": list(self.internal_doc_ids),
            "excluded_doc_ids": list(self.excluded_doc_ids),
            "calls": self.calls,
            "items": len(self.items),
            "discarded": len(self.discarded),
            "skipped_reason": self.skipped_reason,
        }


class GapRow(BaseModel):
    approach: str
    doc_ids: list[str]
    limitation: str
    our_difference: str


class GapTable(BaseModel):
    rows: list[GapRow] = Field(default_factory=list)
    alerts: list[OverlapAlert] = Field(default_factory=list)
