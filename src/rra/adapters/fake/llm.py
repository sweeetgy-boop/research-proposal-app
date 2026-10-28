"""결정적 가짜 LLM — 작성(섹션별 JSON)·검토(의견 JSON). 프롬프트의 [섹션: key] 를 읽어 답한다."""

from __future__ import annotations

import json
import re

_SECTION = re.compile(r"\[섹션: ([a-z_]+)\]")
_SENT_ID = re.compile(r'"sentence_id": "(s:[a-z_]+:\d+)"')
_EVIDENCE = re.compile(r'<doc id="([^"<>]+)"')
_STRUCTURE_HEAD = "[자유 입력"  # U2 간편 입력 프롬프트 머리
_BRIEF_HEAD = "[선행연구"  # U5 브리핑 프롬프트 구획 머리
_FIGURE_HEAD = re.compile(r"^\[그림 명세: ([a-z_]+)\]")  # [G] 그림 명세 프롬프트 머리
_FIGURE_EDIT_HEAD = "[그림 수정:"  # [G][2] 말로 고치기 — 명세 변경 프롬프트 머리
_PICK_HEAD = "[분석 기법 추천]"  # [11] 기법 고르기
_TECH_HEAD = re.compile(r"^\[분석 기법: ([a-z_]+)\]")  # [11] 기법 분석
_EDIT_REQUEST = re.compile(r"<request>(.*?)</request>", re.S)
_FREE_TEXT = re.compile(r'"text": "([^"]*)"')


def _structure_answer(prompt: str) -> str:
    """U2: 자유 문장의 첫 문장을 현황 칸에, 둘째 문장을 목표 칸에 (원문 그대로 → 근거 검사 통과).
    나머지 칸은 비워 보완 질문이 나오게 한다."""
    m = _FREE_TEXT.search(prompt)
    text = m.group(1) if m else ""
    parts = [p.strip() for p in re.split(r"(?<=[.。!?])\s+", text) if p.strip()]
    return json.dumps(
        {
            "current_state": parts[0] if parts else "",
            "root_cause": "",
            "limitation": "",
            "goal": parts[1] if len(parts) > 1 else "",
        },
        ensure_ascii=False,
    )


def _brief_answer(prompt: str) -> str:
    """U5: 구획마다 한 줄 요약(수치 없음), 첫 구획을 근거로 한 공백 후보 하나."""
    ids = _EVIDENCE.findall(prompt)
    return json.dumps(
        {
            "summaries": [
                {"chunk_id": i, "summary": "궤도 상태 감지와 열화 추정을 다룸."} for i in ids
            ],
            "gaps": (
                [{"text": "재래선 구간의 열화 진행 속도 자료가 없음.", "evidence": ids[:1]}]
                if ids
                else []
            ),
        },
        ensure_ascii=False,
    )


def _figure_answer(kind: str) -> str:
    """[G] 가짜 그림 명세 — 글자는 가짜 초안 문장(아래 texts)·고정 라벨 안에서만 (검사 통과)."""
    specs = {
        "concept": {
            "boxes": [
                {"label": "현황", "lines": ["궤도 틀림 반복"]},
                {"label": "문제", "lines": ["다짐 효과 지속 기간"]},
                {"label": "해결 방안", "lines": ["검측 이력 분석", "진행 속도 추정"]},
                {"label": "기대효과", "lines": ["유지보수 비용 절감"]},
            ]
        },
        "process": {
            "stages": [
                {"name": "검측 이력 분석", "outputs": ["구간별 진행 속도"]},
                {"name": "다짐 효과 분석", "outputs": ["지속 기간"]},
                {"name": "보수 우선순위 산정", "outputs": ["산정 방법"]},
            ]
        },
        "roadmap": {
            "metrics": [{"name": "열화 예측 기술 확보", "target": "목표치 확인 필요"}],
            "stages": [{"name": "시설처 유지보수 계획 반영"}, {"name": "현장 적용"}],
        },
        # v2 [3] — 글자는 가짜 초안 문장 구절 (30자 안)
        "as_is_to_be": {
            "as_is": [
                {"tag": "현황", "text": "궤도 틀림 진행 속도"},
                {"tag": "원인", "text": "다짐 효과 지속 기간"},
                {"tag": "한계", "text": "선행연구는 틀림 진행 속도를 다루지 않음"},
            ],
            "to_be": [
                {"tag": "목표", "text": "보수 우선순위를 산정함"},
                {"tag": "해결 방안", "text": "검측 이력을 분석해 구간별 진행 속도를 추정함"},
                {"tag": "기대효과", "text": "유지보수 비용을 절감함"},
            ],
            "solution": "이력 기반 열화 예측",
        },
        "comparison": {
            "aspects": ["연구목표", "연구방법"],
            "projects": [{"title": "궤도 상태 자동 감지 연구", "cells": {"연구목표": "정보 없음"}}],
            "proposal": {
                "title": "제안 과제",
                "cells": {"연구목표": "보수 우선순위 산정", "연구방법": "검측 이력 분석"},
            },
        },
    }
    if kind not in specs:
        return json.dumps({"skip": "no_facts" if kind == "stat_chart" else "no_period"})
    return json.dumps(specs[kind], ensure_ascii=False)


# [11] 가짜 기법 추천 — SWOT(2-가-(2))·비용-편익(3-가) 두 개. 항목은 가짜 초안 문장과 그 id
_FAKE_PICKS = {
    "picks": [
        {"technique": "swot", "reason": "공사 검측 자료(강점)와 선행연구 공백(기회)이 함께 있음"},
        {"technique": "cost_benefit", "reason": "기대효과에 유지보수 비용 절감이 있음"},
    ],
    "none_reason": "",
}
_FAKE_TECHNIQUES = {
    "swot": {
        "groups": [
            {
                "name": "강점",
                "items": [{"text": "검측 이력 분석", "rating": "상", "source": "s:method:0"}],
            },
            {
                "name": "약점",
                "items": [{"text": "다짐 효과 지속 기간", "rating": "중", "source": "s:method:1"}],
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
                    {"text": "보수 횟수", "rating": "하", "source": "s:expected_management:0"}
                ],
            },
        ]
    },
    "cost_benefit": {
        "groups": [
            {
                "name": "비용",
                "items": [
                    {"text": "검측 이력 분석", "amount": "산출 필요", "source": "s:method:0"}
                ],
            },
            {
                "name": "편익",
                "items": [
                    {
                        "text": "유지보수 비용을 절감함",
                        "amount": "산출 필요",
                        "source": "s:expected_management:0",
                    }
                ],
            },
        ]
    },
    "pugh": {
        "columns": ["현행 방식", "제안 방식"],
        "rows": [
            {"name": "구간별 진행 속도", "cells": ["0", "+"], "source": "s:method:0"},
            {"name": "다짐 효과 지속 기간", "cells": ["0", "+"], "source": "s:method:1"},
        ],
    },
}


def _technique_answer(key: str) -> str:
    """[11] 가짜 기법 분석 — 목록에 없는 기법은 skip(해당 없음)."""
    if key not in _FAKE_TECHNIQUES:
        return json.dumps({"skip": "가짜 모드에 없는 기법"}, ensure_ascii=False)
    return json.dumps(_FAKE_TECHNIQUES[key], ensure_ascii=False)


class ScriptedComposeLLM:
    """섹션 키에 따라 한국어 문장 1~2개를 JSON 으로 돌려준다. 근거는 프롬프트의 첫 구획 id."""

    model_name = "fake/compose"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def aclose(self) -> None:  # 조립이 종료 때 부른다 (실 어댑터와 같은 모양)
        return None

    async def complete(self, prompt, *, system=None, max_tokens=None, json_mode=False) -> str:
        self.calls.append(prompt)
        if prompt.startswith(_STRUCTURE_HEAD):
            return _structure_answer(prompt)
        if _BRIEF_HEAD in prompt and "summaries" in prompt:
            return _brief_answer(prompt)
        if prompt.startswith(_FIGURE_EDIT_HEAD):  # 가짜: 명세 그대로, 요청을 모양 요청으로
            m = _EDIT_REQUEST.search(prompt)
            style = (m.group(1) if m else "").strip()[:200]
            return json.dumps(
                {"spec": None, "style": style, "summary": [f"모양: {style}"]}, ensure_ascii=False
            )
        fm = _FIGURE_HEAD.match(prompt)
        if fm:
            return _figure_answer(fm.group(1))
        if prompt.startswith(_PICK_HEAD):
            return json.dumps(_FAKE_PICKS, ensure_ascii=False)
        tm = _TECH_HEAD.match(prompt)
        if tm:
            return _technique_answer(tm.group(1))
        m = _SECTION.search(prompt)
        key = m.group(1) if m else "method"
        ids = _EVIDENCE.findall(prompt)
        ev = [ids[0]] if ids else []
        if key == "task_type":
            return json.dumps(
                {
                    "choices": ["applied"],
                    "sentences": [{"text": "현장 적용을 전제로 한 응용연구임.", "evidence": []}],
                },
                ensure_ascii=False,
            )
        if key == "utilization":
            return json.dumps(
                {
                    "choices": ["facility_method", "software"],
                    "sentences": [
                        {
                            "text": "개발한 산정 방법을 시설처 유지보수 계획에 반영함.",
                            "evidence": [],
                        }
                    ],
                },
                ensure_ascii=False,
            )
        if key == "strategy_alignment":
            return json.dumps({"choices": [], "sentences": []}, ensure_ascii=False)
        if key == "title":
            return json.dumps(
                [{"text": "궤도 검측 이력 기반 보수 우선순위 산정 방법 개발", "evidence": []}],
                ensure_ascii=False,
            )
        texts = {
            "policy_importance": ["제안자가 적은 정책 근거에 부합하는 과제임."],
            "tech_importance": [
                "선행연구는 틀림 진행 속도를 다루지 않음.",
                "본 연구는 다짐 효과 지속 기간을 반영함.",
            ],
            "objective": ["궤도 틀림 진행 속도를 추정해 보수 우선순위를 산정함."],
            "method": [
                "검측 이력을 분석해 구간별 진행 속도를 추정함.",
                "다짐 효과의 지속 기간을 분석함.",
            ],
            "expected_management": ["보수 횟수를 줄여 유지보수 비용을 절감함."],
            "expected_technology": ["이력 기반 열화 예측 기술을 확보함."],
            "expected_standing": ["철도 안전 관리 수준을 대외에 입증함."],
            "overlap_review": ["유사과제 검토 결과 중복 기준을 넘는 과제는 없음."],
        }
        return json.dumps(
            [
                {"text": t, "evidence": ev if key in ("tech_importance", "overlap_review") else []}
                for t in texts.get(key, ["내용임."])
            ],
            ensure_ascii=False,
        )


class ScriptedReviewLLM:
    """보낸 문장 중 method 섹션 첫 문장에 수정안 하나, 전체 의견 하나를 돌려준다."""

    model_name = "fake/review"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def aclose(self) -> None:
        return None

    async def complete(self, prompt, *, system=None, max_tokens=None, json_mode=False) -> str:
        self.calls.append(prompt)
        ids = _SENT_ID.findall(prompt)
        target = next((i for i in ids if i.startswith("s:method:")), ids[0] if ids else None)
        sentences = []
        if target:
            sentences.append(
                {
                    "sentence_id": target,
                    "issue_type": "문장",
                    "comment": "주어와 수치 없이 서술이 모호함 — 분석 대상을 명시",
                    "revised_text": "경부선 구간의 검측 이력을 분석해 구간별 진행 속도를 추정함.",
                    "evidence": [],
                }
            )
        return json.dumps(
            {
                "sentences": sentences,
                "sections": [{"section": "method", "comment": "연차별 산출물을 적을 것"}],
                "resolved": [],
            },
            ensure_ascii=False,
        )
