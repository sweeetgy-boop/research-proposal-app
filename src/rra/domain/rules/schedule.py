"""U6 추진일정·성과지표의 순수 규칙.

- research_period_months: 제안자 입력(constraints)에서 연구기간(개월)을 읽는다 — "24개월", "2년",
  "1년 6개월", "연구기간 3년". 없으면 None.
- schedule_months: 연구방법 본문에서 단계별 기간(개월)을 모아 합산한다 — "(6개월)", "1~6개월",
  "7~12개월" 같은 구간은 길이로, "3개월" 은 그대로. "N차년도" 는 12개월로 본다.
- schedule_problems: 합산이 연구기간을 넘으면 경고 schedule_exceeds_period (문장은 그대로).
"""

from __future__ import annotations

import re

from rra.domain.models import Draft
from rra.domain.rules.lint import LintProblem

SCHEDULE_EXCEEDS = "schedule_exceeds_period"
TARGET_UNKNOWN = "목표치 확인 필요"
SCHEDULE_SECTION = "method"
METRIC_SECTIONS: tuple[str, ...] = (
    "expected_management",
    "expected_technology",
    "expected_standing",
)

_PERIOD = re.compile(
    r"(?:연구\s*기간|기간|수행\s*기간)?\s*(?:총\s*)?"
    r"(?:(\d{1,2})\s*년)?\s*(?:(\d{1,3})\s*개월)?"
)
_YEARS = re.compile(r"(\d{1,2})\s*년(?:\s*(\d{1,2})\s*개월)?")
_MONTHS = re.compile(r"(\d{1,3})\s*개월")
_RANGE = re.compile(r"(\d{1,3})\s*[~∼－-]\s*(\d{1,3})\s*개월")
_YEAR_STEP = re.compile(r"(\d)\s*차\s*년도")


def research_period_months(constraints: str) -> int | None:
    """제약 문장에서 연구기간(개월). 연·개월 조합 중 가장 큰 값 하나. 없으면 None."""
    text = constraints or ""
    best: int | None = None
    for m in _YEARS.finditer(text):
        months = int(m.group(1)) * 12 + int(m.group(2) or 0)
        best = max(best or 0, months)
    for m in _MONTHS.finditer(text):
        months = int(m.group(1))
        if months >= 3:  # "2개월 내 착수" 같은 짧은 조건은 기간으로 보지 않는다
            best = max(best or 0, months)
    return best if best and best > 0 else None


def schedule_months(text: str) -> int:
    """본문에 적힌 단계별 기간(개월)의 합. 구간 "a~b개월" 은 (b-a+1), 단독 "N개월" 은 N.
    같은 숫자가 구간과 단독으로 겹치지 않도록 구간을 먼저 지운다. "N차년도" 는 12개월씩."""
    body = text or ""
    total = 0
    for m in _RANGE.finditer(body):
        a, b = int(m.group(1)), int(m.group(2))
        if b >= a:
            total += b - a + 1
    body = _RANGE.sub(" ", body)
    total += sum(int(m.group(1)) for m in _MONTHS.finditer(body))
    steps = {int(m.group(1)) for m in _YEAR_STEP.finditer(body)}
    if steps and total == 0:
        total = max(steps) * 12
    return total


def schedule_problems(draft: Draft) -> list[LintProblem]:
    """연구기간이 입력에 있고 연구방법의 일정 합이 그보다 크면 경고 1건 (섹션 단위)."""
    period = research_period_months(draft.request.constraints)
    if period is None:
        return []
    sec = draft.section(SCHEDULE_SECTION)
    if sec is None or not sec.sentences:
        return []
    planned = schedule_months(sec.text)
    if planned <= period:
        return []
    return [
        LintProblem(
            section=SCHEDULE_SECTION,
            code=SCHEDULE_EXCEEDS,
            message=f"추진일정 합계 {planned}개월 > 연구기간 {period}개월 — 단계 기간을 조정할 것",
            severity="warning",
        )
    ]


def schedule_instruction(period: int) -> str:
    return (
        "[추진일정 — 연구기간 안에서]\n"
        f"제안자 입력의 연구기간은 {period}개월이다. 단계별 추진일정을 개월 단위로 적되(예: "
        '"1~6개월: …", "7~12개월: …") 단계 기간의 합이 연구기간을 넘지 않게 한다. '
        "기간 밖의 수치는 쓰지 않는다."
    )


def metric_instruction() -> str:
    return (
        "[성과지표 — 측정 방법과 함께]\n"
        "이 섹션의 효과마다 성과지표(무엇을 재는지)와 측정 방법(언제·어떻게)을 한 문장 안에 "
        "적는다. "
        "목표치(수치)는 제안자 입력이나 자료에 있을 때만 쓰고, 없으면 수치 대신 문자 그대로 "
        f'"{TARGET_UNKNOWN}" 라고 적는다.'
    )
