"""U8 시범운영 측정 기록 — runs/<user>/<run_id>/usage.json.

단계별 소요 시간, 필수 요소 충족률(검토 checklist_coverage 가 있을 때), 근거 판단 비율, 다시 쓰기
횟수, HWPX 성공 여부, 만족도(1~5 + 한 줄). 개인정보·본문은 담지 않는다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

MAX_FEEDBACK_CHARS = 200
_CONTACT_HINTS = ("@", "010-", "02-", "031-", "042-")


class Satisfaction(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=MAX_FEEDBACK_CHARS)
    recorded_at: str | None = None

    @field_validator("comment")
    @classmethod
    def _no_contact(cls, v: str) -> str:
        v = " ".join(v.split())
        if any(h in v for h in _CONTACT_HINTS):
            raise ValueError("만족도 한 줄에는 이메일·전화번호를 적지 않습니다.")
        return v


class EvidenceCounts(BaseModel):
    approve: int = 0
    replace: int = 0
    exclude: int = 0
    total: int = 0  # 판단 대상 근거 참조 수 (문장×근거 id)

    def ratios(self) -> dict[str, float]:
        if self.total <= 0:
            return {"approve": 0.0, "replace": 0.0, "exclude": 0.0}
        return {
            "approve": round(self.approve / self.total, 3),
            "replace": round(self.replace / self.total, 3),
            "exclude": round(self.exclude / self.total, 3),
        }


class UsageRecord(BaseModel):
    run_id: str
    step_seconds: dict[str, float] = Field(default_factory=dict)  # step 이름 → 초
    total_seconds: float | None = None
    checklist_coverage: float | None = None  # 검토 결과에 있을 때만 (0~1)
    evidence: EvidenceCounts = Field(default_factory=EvidenceCounts)
    rewrites: int = 0  # AI 다시 쓰기 반영 횟수
    hwpx_success: bool | None = None  # finalize 성공 여부 (None = 아직)
    satisfaction: Satisfaction | None = None
    updated_at: str | None = None
