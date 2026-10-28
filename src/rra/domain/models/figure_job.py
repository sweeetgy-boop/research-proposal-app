"""그림 백그라운드 작업(ADR 0045) — 초안 글을 먼저 보이고 그림은 뒤에서 그린다.

run 하나에 작업 파일 하나(figures_job.json). 버전 파일은 그리는 동안 바꾸지 않는다 — 읽을 때 작업의
그림을 합치고(`rules/figure_job.merge_figures`), 작업이 끝나면 그동안 만든 버전 파일에 한 번 채운다.
상태 파일(state.json)이 아니라 따로 두는 이유: 다른 동작(편집·다시 쓰기)이 들고 있던 옛 상태를
저장해도 그림 진행 상태가 되돌아가지 않게.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .figure import Figure

FigureJobStatus = Literal["pending", "drawing", "done", "failed"]
SlotStatus = Literal["drawing", "done", "failed", "skipped"]


class FigureSlot(BaseModel):
    """그림 한 장의 자리 — 그리는 동안 카드에 "그림 준비 중" 으로 보인다."""

    slot_id: str  # "slot-1" … (그림 id 는 다 그린 뒤에 정해진다)
    kind: str  # 그림 종류 (as_is_to_be·schedule·technique …)
    section: str  # 그림이 붙는 섹션 (분석 기법 추천 자리는 빈 값 — 섹션을 아직 모른다)
    display_name: str  # 화면 이름 (한국어)
    status: SlotStatus = "drawing"
    figure_id: str | None = None  # 다 그린 그림의 id
    reason: str | None = None  # 실패·건너뜀 사유 코드 (예외 클래스명·검사 코드, 원문 없음)


class FigureJob(BaseModel):
    status: FigureJobStatus = "pending"
    base_version: int = 1  # 그림을 계획한 버전 (섹션 글은 이 버전 것)
    slots: list[FigureSlot] = Field(default_factory=list)
    figures: list[Figure] = Field(default_factory=list)  # 다 그린 그림 (도착 순)
    techniques: dict[str, Any] | None = None  # TechniqueOutcome.model_dump()
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    submitted_at: str | None = None  # run 을 만든 때 (시간 측정 기준)
    draft_visible_seconds: float | None = None  # 제출 → 초안 글 보임(drafted)
    figures_done_seconds: float | None = None  # 제출 → 그림 모두 끝남
    error: str | None = None  # 작업 전체 실패 사유 (예외 클래스명·interrupted)
    applied: bool = False  # 끝난 뒤 그동안 만든 버전 파일에 그림을 채웠다
