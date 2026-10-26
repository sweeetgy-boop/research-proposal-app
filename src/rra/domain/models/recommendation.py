"""차별화 과제 추천 — 유사과제 확인 직후, 기존 과제와 차별성을 갖는 과제 0~5건 (ADR 0012).

LLM 출력을 검증한 뒤의 값만 이 모델에 들어온다. 본문은 비신뢰 텍스트(외부 LLM 출력)이고,
run 에는 `RecommendationResult.transfer()`(doc_id·개수만)가 manifest 에, 전체는
runs/<user>/<run_id>/recommendations.json 에 남는다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

MAX_RECOMMENDATIONS = 5
MAX_REASONS = 3
MAX_REC_CHARS = 600
MAX_TITLE_CHARS = 200


class ProjectRecommendation(BaseModel):
    """추천 과제 하나 (검증 통과분)."""

    title: str = Field(min_length=1, max_length=MAX_TITLE_CHARS)  # 가제
    summary: str = Field(min_length=1, max_length=MAX_REC_CHARS)  # 한두 문장
    # 기존 과제 대비 핵심 차별점
    differentiation: str = Field(min_length=1, max_length=MAX_REC_CHARS)
    reasons: list[str] = Field(min_length=1, max_length=MAX_REASONS)  # 어떤 과제와 무엇이 다른지
    build_on: str = Field(default="", max_length=MAX_REC_CHARS)  # 이어받을 기존 성과
    risks: str = Field(default="", max_length=MAX_REC_CHARS)  # 예상 위험·확인할 점
    compared_with: list[str] = Field(default_factory=list)  # 비교한 기존 과제 doc_id (precheck 안)
    evidence: list[str] = Field(default_factory=list)  # 근거 doc_id (검색·precheck 안)

    def self_check_text(self) -> str:
        """자기 중복 검사(precheck)에 넣는 글 — 가제·요약·차별점."""
        return " ".join(t for t in (self.title, self.summary, self.differentiation) if t)


class RecommendationResult(BaseModel):
    """추천 결과 + 외부 전송 범위. recommendations 가 비면 no_recommendation_reason 이 있다."""

    recommendations: list[ProjectRecommendation] = Field(
        default_factory=list, max_length=MAX_RECOMMENDATIONS
    )
    no_recommendation_reason: str | None = Field(default=None, max_length=MAX_REC_CHARS)
    discarded: list[dict[str, str]] = Field(default_factory=list)  # {title, reason}
    provider: str | None = None
    model: str | None = None
    fallback_local: bool = False  # recommend 단계 키가 없어 로컬(compose) 모델로 돌림
    public_doc_ids: list[str] = Field(default_factory=list)
    internal_doc_ids: list[str] = Field(default_factory=list)
    excluded_doc_ids: list[str] = Field(default_factory=list)  # include_internal=false 로 뺀 것
    calls: int = 0  # 외부 LLM 호출 수 (자기 중복 검사는 로컬이라 세지 않는다)
    skipped_reason: str | None = None  # no_alerts_or_evidence | no_documents | parse_failed

    def transfer(self) -> dict[str, object]:
        """manifest 에 남기는 전송 기록 (본문 없음)."""
        return {
            "provider": self.provider,
            "model": self.model,
            "fallback_local": self.fallback_local,
            "public_doc_ids": list(self.public_doc_ids),
            "internal_doc_ids": list(self.internal_doc_ids),
            "excluded_doc_ids": list(self.excluded_doc_ids),
            "calls": self.calls,
            "recommendations": len(self.recommendations),
            "discarded": len(self.discarded),
            "skipped_reason": self.skipped_reason,
        }


class RecommendationPreview(BaseModel):
    """추천 하나를 제안자 입력에 반영한 '수정 전 미리보기'.

    사용자가 고쳐 확정한 입력으로 초안을 만든다.
    """

    index: int
    title_hint: str
    goal: str
    differentiation: str
    changed: list[str]  # 바뀐 입력 칸 이름
