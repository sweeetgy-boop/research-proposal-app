"""상태 표시(확인 기록) — 버전을 만들지 않고 현재 버전에 덧붙는 표시 (2026-10-28 레인 D, ADR 0042).

그림 확인함·근거 승인/제외·선택형 확정·추천 그림 넣기 확정/필요 없음/다시 넣기·로컬 검토 제안 [무시]
는
내용이 아니라 "제안자가 확인했다" 는 표시다. 버전 파일(draft_vN.json)은 만든 뒤 바꾸지 않고, 표시는
버전마다 따로 둔 표시 파일(versions/marks_vN.json)에 쌓는다. 읽을 때 RunManager 가 버전 + 표시를
합쳐(domain/rules/status_marks.apply_marks) 화면·제출 전 점검·마무리(HWPX)에 넘긴다. 내용이 바뀌어
새 버전을 만들 때는 합친 현재 버전에서 출발하므로 표시가 새 버전 파일에 그대로 들어간다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .figure import RecommendationStatus
from .review import EvidenceDecision

MarkKind = Literal[
    "figure_confirm",  # 그림 [확인함]
    "figure_accept",  # 추천 그림 [넣기 확정]
    "figure_dismiss",  # 추천 그림 [필요 없음]
    "figure_restore",  # 추천 그림 [다시 넣기]
    "evidence_approve",  # 근거 승인
    "evidence_exclude",  # 근거 제외
    "choice_confirm",  # 선택형 확정
    "suggestion_ignore",  # 로컬 검토 제안 [무시] (레인 B)
]
MARK_LABELS: dict[str, str] = {
    "figure_confirm": "그림 확인",
    "figure_accept": "추천 그림 넣기 확정",
    "figure_dismiss": "추천 그림 필요 없음",
    "figure_restore": "추천 그림 다시 넣기",
    "evidence_approve": "근거 승인",
    "evidence_exclude": "근거 제외",
    "choice_confirm": "선택형 확정",
    "suggestion_ignore": "검토 제안 무시",
}
MAX_MARK_LOG = 500


class StatusMark(BaseModel):
    """확인 기록 한 줄 — 무엇을(target) 언제 표시했는가. label 은 화면 표시용 이름(그림 이름 등)."""

    kind: MarkKind
    target: str = Field(default="", max_length=200)  # 그림 id·문장 id·섹션 key (화면에는 label)
    label: str = Field(default="", max_length=200)
    at: str | None = None


class FigureMark(BaseModel):
    """그림 하나의 상태 표시. image_sha 는 표시한 때의 그림 — 그 뒤 그림이 바뀌었으면 표시를
    적용하지 않는다(새 그림은 다시 확인해야 한다)."""

    image_sha: str | None = None
    confirmed: bool | None = None
    included: bool | None = None
    recommendation_status: RecommendationStatus | None = None
    recommendation_at: str | None = None


class VersionMarks(BaseModel):
    version: int = Field(ge=1)
    figures: dict[str, FigureMark] = Field(default_factory=dict)
    # 근거 판단 전체 목록(승인·제외). None 이면 버전 파일의 목록 그대로
    evidence_decisions: list[EvidenceDecision] | None = None
    log: list[StatusMark] = Field(default_factory=list)
    updated_at: str | None = None

    @property
    def empty(self) -> bool:
        return not self.figures and self.evidence_decisions is None and not self.log
