"""지어낸 수치 검사 — 문장의 수치가 제안자 입력이나 그 문장이 인용한 근거 청크에 없으면 경고.

약한 모델은 "약 10% 절감", "2년 동안" 처럼 근거 없는 수치를 그럴듯하게 붙인다. 폐기하지 않고
lint 경고(unsupported_number)로 담당자가 보게 한다 (lint.number_checked 섹션만).

뽑는 대상: 숫자(천 단위 쉼표·소수 허용) + 바로 뒤 단위. 영문자·`#`·`/` 뒤의 숫자(문서 id, 식별자)는
제외한다. 단위가 같은 종류면 환산해 비교한다 — "1년 이내" 가 입력에 있으면 "12개월" 은 통과.

- 기간: 년·개년·년간 → 개월×12, 개월·달 → 개월 / 주·주일 → 일×7, 일·일간 → 일 / 시간
- 금액: 원·천원·만원·백만원·천만원·억원 → 원
- 비율: %·퍼센트
- 개수: 건·회·개·명·개소·대 (단위마다 따로)
- 연도 표기(1900~2100년)·월·차(차년도)는 환산 없이 그대로 대조
- 단위 없는 숫자는 허용 텍스트의 어떤 수치든 같은 값이면 통과 (0.80 같은 임계치·계수)

한계: 어절 단위 패턴이라 "열 개", "백만 원" 같은 한글 수사는 뽑지 못한다. 수치가 허용 텍스트에
있어도 다른 뜻으로 쓰인 것은 잡지 못한다 — 폐기가 아닌 경고인 이유다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

_NUM = r"\d+(?:,\d{3})*(?:\.\d+)?"
# 긴 단위를 먼저 (개년 > 년, 백만원 > 만원 > 원, 주일 > 주, 일간 > 일)
_UNIT = (
    r"%|퍼센트|개년|년간|년도|년|개월|달|주일|주|일간|일|시간|월|차년도|차"
    r"|억원|천만원|백만원|만원|천원|원|건|회|개소|개|명|대|톤|km"
)
_NUMBER = re.compile(rf"(?<![A-Za-z0-9#/_.\-]){_NUM}(?:\s?(?:{_UNIT}))?(?![A-Za-z])")
_SPLIT = re.compile(rf"({_NUM})\s?({_UNIT})?\Z")

_MONTHS = {"년": 12, "개년": 12, "년간": 12, "개월": 1, "달": 1}
_DAYS = {"일": 1, "일간": 1, "주": 7, "주일": 7}
_WON = {
    "원": 1,
    "천원": 1_000,
    "만원": 10_000,
    "백만원": 1_000_000,
    "천만원": 10_000_000,
    "억원": 100_000_000,
}
_YEAR_MIN, _YEAR_MAX = 1900, 2100

Canonical = tuple[str, Decimal]


def _parse(match: str) -> tuple[Decimal, str] | None:
    m = _SPLIT.match(match)
    if m is None:
        return None
    try:
        value = Decimal(m.group(1).replace(",", ""))
    except InvalidOperation:
        return None
    return value, m.group(2) or ""


def _canonical(value: Decimal, unit: str) -> Canonical:
    if unit in ("%", "퍼센트"):
        return "pct", value
    if (
        unit in ("년", "년도")
        and _YEAR_MIN <= value <= _YEAR_MAX
        and value == value.to_integral_value()
    ):
        return "year", value  # 연도 표기 — 기간이 아니다
    if unit in _MONTHS:
        return "month", value * _MONTHS[unit]
    if unit in _DAYS:
        return "day", value * _DAYS[unit]
    if unit in _WON:
        return "won", value * _WON[unit]
    if unit in ("차", "차년도"):
        return "ord", value
    if unit == "":
        return "bare", value
    return f"unit:{unit}", value


def _norm(c: Canonical) -> Canonical:
    kind, v = c
    return kind, v.normalize()


def numbers(text: str) -> list[tuple[str, Canonical]]:
    """문장의 수치 표기 → [(표기 원문, 정규화 값)]. 순서 유지."""
    out: list[tuple[str, Canonical]] = []
    for m in _NUMBER.finditer(text):
        parsed = _parse(m.group(0))
        if parsed is None:
            continue
        value, unit = parsed
        out.append((m.group(0).replace(" ", ""), _norm(_canonical(value, unit))))
    return out


def unsupported_numbers(text: str, allowed_texts: Iterable[str]) -> list[str]:
    """허용 텍스트(입력·인용 근거)에 같은 값(단위 환산 후)이 없는 수치 표기. 비어 있으면 통과."""
    allowed: set[Canonical] = set()
    for t in allowed_texts:
        allowed.update(c for _, c in numbers(t or ""))
    values = {v for _, v in allowed}
    out: list[str] = []
    for shown, canon in numbers(text):
        kind, value = canon
        ok = canon in allowed or ("bare", value) in allowed or (kind == "bare" and value in values)
        if not ok and shown not in out:
            out.append(shown)
    return out
