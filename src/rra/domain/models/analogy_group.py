"""비슷한 유추 자료 묶음의 비교 분석 결과 (ADR 0065, 계약 problem-card.md 4.6절).

글 칸은 모두 검증(`domain/rules/analogy_group.check_analysis`)을 지난 AI 출력이다 — 비신뢰 텍스트로
다룬다. 초록으로 알 수 없는 칸은 정해진 문구(`rules.analogy_group.NEEDS_SOURCE`) 하나로 통일한다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

GroupStatus = Literal["ok", "failed", "skipped", "off"]
GROUP_FIELDS = ("core_method", "difference", "use", "limit")


class GroupItem(BaseModel):
    """자료 한 건의 비교 행. 제목·자료원·주소는 진입점이 저장소에서 다시 읽은 문서로 채운다."""

    doc_id: str
    core_method: str  # 핵심 방식
    difference: str  # 다른 자료와 다른 점
    use: str  # 이 과제에 활용할 점 — 늘 '추정'
    limit: str  # 한계


class GroupSummary(BaseModel):
    common: str  # 공통 접근
    gap: str  # 아직 다뤄지지 않은 부분


class GroupDoc(BaseModel):
    """분석한 자료의 표시 정보 — 서버가 그 사용자가 볼 수 있는 저장소에서 다시 읽은 값."""

    doc_id: str
    title: str  # 수집 문서 제목 (비신뢰)
    source: str = ""
    source_label: str = ""
    url: str | None = None
    year: int | None = None


class GroupAnalysis(BaseModel):
    """묶음 한 개의 비교 분석 결과. status 가 ok 가 아니면 items·summary 는 비어 있다."""

    status: GroupStatus
    group_id: str | None = None
    docs: list[GroupDoc] = Field(default_factory=list)  # items 와 같은 순서
    items: list[GroupItem] = Field(default_factory=list)
    summary: GroupSummary | None = None
    cached: bool = False
    seconds: float = 0.0
    reason: str | None = None  # 실패 사유 코드(기록용 — 화면에는 문구로)
    replaced: int = 0  # 검증이 문구로 바꾼 칸 수(기록용)
    prompt_chars: int = 0  # 보낸 글자 수(기록용, 본문 없음)
    output_chars: int = 0
