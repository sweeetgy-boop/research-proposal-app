"""양식의 선택형 항목 — 과제유형(1-다), 활용계획 체크(4), 경영전략 정합성(2-가-(3)).

LLM 은 이 목록 안에서만 제안하고(Section.choices), 확정은 사용자가 한다(Confirmation).
선택지 id 는 앱이 정한 값이라 프롬프트에서 비신뢰 구획 밖에 둔다.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TASK_TYPES: dict[str, str] = {
    "basic": "기초연구",
    "applied": "응용연구",
    "development": "개발연구",
}

# 양식 4. 연구결과 활용계획 가~차 (순서 유지)
UTILIZATION: dict[str, str] = {
    "strategy_plan": "가. 중장기 전략 및 주요업무계획 반영",
    "regulation": "나. 제도(규정 및 업무처리 기준 등) 제·개정",
    "feasibility": "다. 사업 타당성 검토 및 경영의사결정 근거자료 활용",
    "negotiation": "라. 외부기관 협상 근거자료 활용",
    "facility_method": "마. 새로운 시설·설비 또는 유지보수 시스템·방법의 개발 및 운영방법 개선",
    "rolling_stock": "바. 차량 및 기존 시설물의 개량 또는 대체",
    "software": "사. 컴퓨터 프로그램의 개발 및 제공",
    "manual": "아. 매뉴얼 작성 및 배포",
    "other": "자. 기타",
    "commercialization": "차. 실용화계획 있음",
}

TASK_TYPES_SOURCE = "task_types"
UTILIZATION_SOURCE = "utilization"
STRATEGY_SOURCE = "strategy_catalog"
STRATEGY_DRAFT_LABEL = "전략체계 초안(확인 전)"
StrategyStatus = Literal["draft", "confirmed"]
OPTION_SOURCES = frozenset({TASK_TYPES_SOURCE, UTILIZATION_SOURCE, STRATEGY_SOURCE})

_ID = re.compile(r"^[A-Za-z0-9-]{1,16}$")


class StrategyTask(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str = Field(max_length=200)

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not _ID.match(v):
            raise ValueError(f"전략 id 형식이 올바르지 않습니다: {v!r}")
        return v


class StrategyDirection(StrategyTask):
    tasks: list[StrategyTask] = Field(default_factory=list)


class StrategyCatalog(BaseModel):
    """코레일 중장기 전략체계 (config/templates/korail_strategy.yaml). 선택지는 전략과제 id."""

    model_config = ConfigDict(frozen=True)

    source: str = ""
    # draft: 공사 홈페이지 자료에서 뽑은 초안(korail_strategy.draft.yaml) —
    # 사람이 `rra strategy promote` 로
    # 확정하기 전. 화면·API 는 "전략체계 초안(확인 전)" 을 함께 보여 준다.
    status: StrategyStatus = "confirmed"
    directions: list[StrategyDirection] = Field(default_factory=list)

    @property
    def label(self) -> str | None:
        return STRATEGY_DRAFT_LABEL if self.status == "draft" else None

    @model_validator(mode="after")
    def _unique(self) -> StrategyCatalog:
        ids = [d.id for d in self.directions] + [t.id for d in self.directions for t in d.tasks]
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup:
            raise ValueError(f"전략 id 중복: {', '.join(dup)}")
        return self

    def options(self) -> dict[str, str]:
        """전략과제 id → "전략방향 > 전략과제"."""
        return {t.id: f"{d.name} > {t.name}" for d in self.directions for t in d.tasks}

    def names(self) -> list[str]:
        tasks = [t.name for d in self.directions for t in d.tasks]
        return [d.name for d in self.directions] + tasks

    def direction_of(self, task_id: str) -> StrategyDirection | None:
        return next((d for d in self.directions if any(t.id == task_id for t in d.tasks)), None)


class Confirmation(BaseModel):
    """사용자가 확정한 선택값. 선택지 id 만 담는다 (개인정보 없음)."""

    choices: dict[str, list[str]] = Field(default_factory=dict)
    updated_at: str | None = None
