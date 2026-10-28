"""[G] 그림 v2 테스트 공용 — 기법 목록(실제 config), 초안·입력·근거, 프롬프트 머리로 답하는
가짜 LLM."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from rra.domain.models import Chunk, ProposalRequest, RetrievalSnapshot, Section, Sentence
from rra.domain.rules.techniques import catalog_from

ROOT = Path(__file__).resolve().parents[1]
CATALOG = catalog_from(
    yaml.safe_load((ROOT / "config/figures/techniques.yaml").read_text(encoding="utf-8"))
)

REQ = ProposalRequest(
    current_state="궤도 틀림이 반복 발생함",
    root_cause="다짐 효과가 오래 가지 않음",
    limitation="주기적 보수로는 진행 속도를 반영하지 못함",
    goal="검측 이력 기반 보수 우선순위 산정",
    constraints="연구기간 24개월",
)
SECTIONS = [
    Section(
        key="tech_importance",
        sentences=[
            Sentence(text="선행연구는 틀림 진행 속도를 다루지 않음.", evidence=["alio:1#0"]),
            Sentence(text="공사는 검측 이력 자료를 축적해 왔음."),
        ],
    ),
    Section(
        key="objective",
        sentences=[Sentence(text="궤도 틀림 진행 속도를 추정해 보수 우선순위를 산정함.")],
    ),
    Section(
        key="method",
        sentences=[
            Sentence(text="검측 이력을 분석해 구간별 진행 속도를 추정함."),
            Sentence(text="현행 주기 보수와 이력 기반 보수를 같은 구간에서 비교함."),
        ],
    ),
    Section(
        key="expected_management",
        sentences=[Sentence(text="보수 횟수를 줄여 유지보수 비용을 절감함.")],
    ),
]
SNAP = RetrievalSnapshot(
    query_hash="q",
    chunks=[
        Chunk(
            chunk_id="alio:1#0",
            doc_id="alio:1",
            ordinal=0,
            text="연간 궤도 보수비는 1,200억 원 수준임.",
        ),
        Chunk(
            chunk_id="own:9#0",
            doc_id="own:9",
            ordinal=0,
            text="비공개 노선 X-9 보수 계획",
            visibility="internal",
        ),
    ],
)
AS_IS = {
    "as_is": [
        {"tag": "현황", "text": "궤도 틀림이 반복 발생함"},
        {"tag": "원인", "text": "다짐 효과가 오래 가지 않음"},
        {"tag": "한계", "text": "주기적 보수로는 진행 속도를 반영하지 못함"},
    ],
    "to_be": [
        {"tag": "목표", "text": "검측 이력 기반 보수 우선순위 산정"},
        {"tag": "해결 방안", "text": "검측 이력을 분석해 구간별 진행 속도를 추정함"},
        {"tag": "기대효과", "text": "유지보수 비용을 절감함"},
    ],
    "solution": "구간별 진행 속도 추정",
}
SWOT = {
    "groups": [
        {
            "name": "강점",
            "items": [
                {
                    "text": "검측 이력 자료를 축적해 왔음",
                    "rating": "상",
                    "source": "s:tech_importance:1",
                }
            ],
        },
        {
            "name": "약점",
            "items": [
                {"text": "다짐 효과가 오래 가지 않음", "rating": "중", "source": "input:root_cause"}
            ],
        },
        {
            "name": "기회",
            "items": [
                {
                    "text": "선행연구는 틀림 진행 속도를 다루지 않음",
                    "rating": "상",
                    "source": "s:tech_importance:0",
                }
            ],
        },
        {
            "name": "위협",
            "items": [
                {"text": "궤도 틀림이 반복 발생함", "rating": "하", "source": "input:current_state"}
            ],
        },
    ]
}
PUGH = {
    "columns": ["현행 방식", "제안 방식"],
    "rows": [
        {"name": "구간별 진행 속도", "cells": ["0", "+"], "source": "s:method:0"},
        {"name": "보수 우선순위", "cells": ["0", "-"], "source": "s:objective:0"},
    ],
}
COST_BENEFIT = {
    "groups": [
        {
            "name": "비용",
            "items": [
                {"text": "연간 궤도 보수비", "amount": "1,200억 원", "source": "alio:1#0"},
                {"text": "검측 이력 분석", "amount": "5억 원", "source": "s:method:0"},
            ],
        },
        {
            "name": "편익",
            "items": [
                {
                    "text": "유지보수 비용을 절감함",
                    "amount": "30% 절감",
                    "source": "s:expected_management:0",
                }
            ],
        },
    ]
}
TECH_ANSWERS = {"swot": SWOT, "pugh": PUGH, "cost_benefit": COST_BENEFIT}
_SPEC_HEAD = re.compile(r"^\[그림 명세: ([a-z_]+)\]")
_TECH_HEAD = re.compile(r"^\[분석 기법: ([a-z_]+)\]")


def js(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


class RoutingLLM:
    """프롬프트 첫 줄로 답을 고른다 — 동시 실행에서도 순서에 기대지 않는다.

    picks: [분석 기법 추천] 답(dict 또는 예외), techniques: key → 답(dict·문자열),
    specs: kind → 그림 명세. fail=True 면 모든 호출이 ConnectionError (Argon 장애 자리)."""

    model_name = "fake/routing"

    def __init__(
        self,
        *,
        picks: Any = None,
        techniques: dict[str, Any] | None = None,
        specs: dict[str, Any] | None = None,
        fail: bool = False,
    ):
        self.picks = picks if picks is not None else {"picks": [], "none_reason": "맞는 기법 없음"}
        self.techniques = dict(TECH_ANSWERS if techniques is None else techniques)
        self.specs = dict({"as_is_to_be": AS_IS} if specs is None else specs)
        self.fail = fail
        self.calls: list[str] = []

    async def complete(self, prompt, *, system=None, max_tokens=None, json_mode=False) -> str:
        self.calls.append(prompt)
        if self.fail:
            raise ConnectionError("down")
        if prompt.startswith("[분석 기법 추천]"):
            return self.picks if isinstance(self.picks, str) else js(self.picks)
        m = _TECH_HEAD.match(prompt)
        if m:
            ans = self.techniques.get(m.group(1), {"skip": "해당 없음"})
            return ans if isinstance(ans, str) else js(ans)
        m = _SPEC_HEAD.match(prompt)
        if m:
            ans = self.specs.get(m.group(1), "{}")
            return ans if isinstance(ans, str) else js(ans)
        return "[]"

    def prompts_for(self, head: str) -> list[str]:
        return [c for c in self.calls if c.startswith(head)]


def picks(*keys: str) -> dict[str, Any]:
    return {
        "picks": [{"technique": k, "reason": f"{k} 가 이 제안에 맞음"} for k in keys],
        "none_reason": "",
    }
