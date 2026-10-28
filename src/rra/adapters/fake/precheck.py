"""가짜 모드 ② 유사과제 흐름 답 (2026-10-28 레인 A) — AI 같음 판정·비교표 원문 추출·[AI로 다듬기]·
차별화 과제안·활용 제안. 프롬프트 머리로 구분하고, 글은 원문·입력에서만 가져와 검증을 통과한다.

- 같음 판정: 첫 후보는 partial, 나머지는 different. 아이디어에 "(중복)" 이 있으면 첫 후보를
same(차단) —
  e2e 의 차단 → [관련 없음] → 차단 해제 경로.
- 과제안: 아이디어에 "(추천 없음)" 이 있으면 0건 + 사유 (e2e "추천 0건" 경로), 아니면 2건.
- 과제안 더 만들기(ADR 0039): "[이미 보인 과제안]" 이 있으면 보인 가제와 다른 안 2건(후보 묶음에서).
- 카드 겹침 확인: 아이디어에 "(과제안 겹침)" 이 있으면 첫 카드 요약에 "(겹침 표본)" 을 넣고,
  겹침 확인은 그
  카드를 "같다" 로 본다. 다시 받기("[겹침을 피해 다시 쓸 안]")는 표본 표시 없는 안 1건.
"""

from __future__ import annotations

import json
import re

JUDGE_HEAD = "[아이디어 — 제안자 입력]"
EXTRACT_HEAD = "[기존 과제]"
POLISH_MARK = "[다듬을 칸]"
RECOMMEND_MARK = "recommendations(0~5개"
CARD_JUDGE_HEAD = "[과제안 겹침 확인]"
SHOWN_MARK = "[이미 보인 과제안]"
REDO_MARK = "[겹침을 피해 다시 쓸 안]"
OVERLAP_SAMPLE = "(겹침 표본)"
_CARD = re.compile(r'<card id="([^"<>]+)">\n(.*?)\n</card>', re.S)
_DOC_CARDS = re.compile(r'<doc id="([^"<>]+)" cards="([^"<>]*)">', re.S)
# [더 만들기] 후보 — 입력 낱말로만 (검증 통과)
_MORE_POOL = [
    (
        "검측 이력과 보수 기록을 함께 본 궤도 보수 시기 판단",
        "검측 이력과 보수 기록으로 보수 시기를 판단함",
    ),
    (
        "구간별 보수 효과 비교로 보수 방법 선택 기준 마련",
        "구간별 보수 효과를 비교해 보수 방법을 고름",
    ),
    ("보수 작업 기록 정리로 보수 우선순위 근거 보강", "보수 작업 기록을 정리해 우선순위 근거로 씀"),
    ("궤도 상태 점검 주기 조정 방안", "궤도 상태에 따라 점검 주기를 조정함"),
    ("다짐 작업 뒤 궤도 상태 변화 추적", "다짐 작업 뒤 궤도 상태가 바뀌는 과정을 추적함"),
    ("보수 우선순위 산정 결과의 현장 검증 절차", "산정한 우선순위를 현장에서 확인하는 절차를 둠"),
]
DIFFERENTIATE_MARK = "items 배열에 과제별"
_DOC = re.compile(r'<doc id="([^"<>]+)"[^>]*>\n(.*?)\n</doc>', re.S)
_INPUT = re.compile(r"<input>\n(.*?)\n</input>", re.S)
_SENT = re.compile(r"(?<=[.。!?])\s+")


def matches(prompt: str) -> str | None:
    if prompt.startswith(CARD_JUDGE_HEAD):
        return card_judge_answer(prompt)
    if prompt.startswith(JUDGE_HEAD):
        return judge_answer(prompt)
    if prompt.startswith(EXTRACT_HEAD):
        return extract_answer(prompt)
    if POLISH_MARK in prompt and "<input>" in prompt:
        return polish_answer(prompt)
    if RECOMMEND_MARK in prompt:
        return recommend_answer(prompt)
    if DIFFERENTIATE_MARK in prompt:
        return differentiate_answer(prompt)
    return None


def judge_answer(prompt: str) -> str:
    ids = [m.group(1) for m in _DOC.finditer(prompt)]
    duplicate = "(중복)" in prompt
    items = []
    for i, doc_id in enumerate(ids):
        if i == 0:
            verdict = "same" if duplicate else "partial"
            reason = (
                "궤도 상태를 감지해 보수 시기를 정하는 대상·문제·방법이 같음"
                if duplicate
                else "궤도 상태 감지라는 대상은 같으나 방법이 다름"
            )
        else:
            verdict, reason = "different", "다루는 대상과 문제가 다름"
        items.append({"doc_id": doc_id, "verdict": verdict, "reason": reason})
    return json.dumps({"items": items}, ensure_ascii=False)


def extract_answer(prompt: str) -> str:
    items = []
    for m in _DOC.finditer(prompt):
        lines = [ln for ln in m.group(2).splitlines() if ln.strip()]
        body = " ".join(ln for ln in lines if not ln.startswith("제목:"))
        first = _SENT.split(body.strip())[0] if body.strip() else ""
        items.append(
            {"doc_id": m.group(1), "objective": first, "method": "", "scope": "", "outcome": ""}
        )
    return json.dumps({"items": items}, ensure_ascii=False)


def polish_answer(prompt: str) -> str:
    m = _INPUT.search(prompt)
    text = " ".join((m.group(1) if m else "").split()).rstrip(". ")
    if text and not text.endswith(("함", "임", "음")):
        text = f"{text} 방안을 마련함"
    return json.dumps({"text": text}, ensure_ascii=False)


def card_judge_answer(prompt: str) -> str:
    cards = {m.group(1): m.group(2) for m in _CARD.finditer(prompt)}
    items = []
    for m in _DOC_CARDS.finditer(prompt):
        for cid in [c for c in m.group(2).split(",") if c]:
            same = OVERLAP_SAMPLE in cards.get(cid, "")
            items.append(
                {
                    "card": cid,
                    "doc_id": m.group(1),
                    "verdict": "same" if same else "different",
                    "reason": "둘 다 궤도 상태 감지로 보수 시기를 정하는 안"
                    if same
                    else "다루는 대상과 방법이 다름",
                }
            )
    return json.dumps({"items": items}, ensure_ascii=False)


def _more_answer(prompt: str, ref: list[str]) -> str:
    shown = prompt.split(SHOWN_MARK, 1)[1]
    fresh = [(t, s) for t, s in _MORE_POOL if t not in shown][:2]
    cards = [
        {
            "title": t,
            "summary": s,
            "goal": s,
            "method": "검측 이력과 보수 이력을 함께 분석함",
            "scope": "일반철도 궤도 구간",
            "differentiation": "기존 과제와 앞서 보인 안이 다루지 않은 보수 판단 기준을 다룸",
            "reasons": ["앞서 보인 안과 분석 대상이 다름"],
            "build_on": "",
            "risks": "",
            "compared_with": ref,
            "evidence": ref,
        }
        for t, s in fresh
    ]
    return json.dumps(
        {
            "recommendations": cards,
            "no_recommendation_reason": None if cards else "더 만들 다른 방향이 없음",
        },
        ensure_ascii=False,
    )


def recommend_answer(prompt: str) -> str:
    if SHOWN_MARK in prompt:
        return _more_answer(prompt, [m.group(1) for m in _DOC.finditer(prompt)][:1])
    if REDO_MARK in prompt:
        ref = [m.group(1) for m in _DOC.finditer(prompt)][:1]
        card = {
            "title": "운행 차량 검측 이력 기반 궤도 틀림 진행 속도 추정 보완안",
            "summary": "검측 이력으로 구간별 진행 속도를 추정해 보수 주기를 정함",
            "goal": "구간별 진행 속도를 추정해 보수 우선순위를 정함",
            "method": "검측 이력을 구간별로 나누어 진행 속도를 추정함",
            "scope": "일반철도 궤도 구간",
            "differentiation": "기존 과제는 상태 감지에 그치나 본 안은 보수 주기까지 정함",
            "reasons": [],
            "build_on": "",
            "risks": "",
            "compared_with": ref,
            "evidence": ref,
        }
        return json.dumps({"recommendations": [card]}, ensure_ascii=False)
    if "(추천 없음)" in prompt:
        return json.dumps(
            {
                "recommendations": [],
                "no_recommendation_reason": "제안 아이디어가 이미 기존 과제와 충분히 다름",
            },
            ensure_ascii=False,
        )
    ids = [m.group(1) for m in _DOC.finditer(prompt)]
    ref = ids[:1]
    cards = [
        {
            "title": "운행 차량 검측 이력 기반 궤도 틀림 진행 속도 추정",
            "summary": "검측 이력으로 구간별 궤도 틀림 진행 속도를 추정함"
            + (f" {OVERLAP_SAMPLE}" if "(과제안 겹침)" in prompt else ""),
            "goal": "구간별 진행 속도를 추정해 보수 우선순위를 정함",
            "method": "검측 이력을 구간별로 나누어 진행 속도를 추정함",
            "scope": "일반철도 궤도 구간",
            "differentiation": "기존 과제는 상태 감지에 그치나 본 안은 진행 속도를 추정함",
            "reasons": ["기존 과제는 진행 속도를 다루지 않음"],
            "build_on": "",
            "risks": "검측 이력의 구간 구분 기준 확인 필요",
            "compared_with": ref,
            "evidence": ref,
        },
        {
            "title": "다짐 효과 지속 기간 반영 보수 주기 산정",
            "summary": "다짐 효과가 이어지는 기간을 반영해 보수 주기를 정함",
            "goal": "다짐 효과 지속 기간을 반영한 보수 주기 산정",
            "method": "보수 이력과 검측 이력을 함께 분석함",
            "scope": "",
            "differentiation": "기존 과제는 보수 뒤 효과 지속 기간을 보지 않음",
            "reasons": ["기존 과제와 분석 대상 기간이 다름"],
            "build_on": "",
            "risks": "",
            "compared_with": ref,
            "evidence": ref,
        },
    ]
    return json.dumps(
        {"recommendations": cards, "no_recommendation_reason": None}, ensure_ascii=False
    )


def differentiate_answer(prompt: str) -> str:
    ids = [m.group(1) for m in _DOC.finditer(prompt)]
    items = [
        {
            "doc_id": doc_id,
            "overlap_summary": "궤도 상태 감지라는 대상이 겹침",
            "build_on": "기존 과제의 감지 결과를 이어받음",
            "differentiation": ["진행 속도 추정으로 넓힘", "보수 우선순위 산정에 씀"],
            "evidence": [doc_id],
        }
        for doc_id in ids
    ]
    return json.dumps({"items": items}, ensure_ascii=False)
