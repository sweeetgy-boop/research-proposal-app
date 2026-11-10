"""TRIZ 40 발명 원리 — 고정 목록 (ADR 0065, 계약 problem-card.md 2절).

AI 가 보낸 원리 이름은 믿지 않는다. 번호(1~40)만 받고 이름은 이 표로 **바꿔 쓴다**. 범위 밖 번호는
버린다. 순수 함수.
"""

from __future__ import annotations

from collections.abc import Iterable

from rra.domain.models.problem_card import MAX_PRINCIPLES, TRIZ_PRINCIPLE_COUNT, TrizPrinciple

PRINCIPLES: dict[int, str] = {
    1: "분할",
    2: "추출",
    3: "국소적 성질",
    4: "비대칭",
    5: "통합",
    6: "범용성",
    7: "포개기",
    8: "평형추",
    9: "선행 반대 조치",
    10: "선행 조치",
    11: "사전 보상",
    12: "등위성",
    13: "역방향",
    14: "곡면화",
    15: "역동성",
    16: "과부족 조치",
    17: "차원 변경",
    18: "기계적 진동",
    19: "주기적 작용",
    20: "유용한 작용의 지속",
    21: "고속 처리",
    22: "전화위복",
    23: "피드백",
    24: "매개체",
    25: "셀프서비스",
    26: "복제",
    27: "일회용품",
    28: "기계 시스템 대체",
    29: "공기·유압 활용",
    30: "유연한 막·얇은 필름",
    31: "다공성 물질",
    32: "색상 변경",
    33: "동질성",
    34: "폐기·재생",
    35: "속성 변환",
    36: "상전이",
    37: "열팽창",
    38: "산화 가속",
    39: "불활성 환경",
    40: "복합 재료",
}


def principle_name(number: int) -> str | None:
    """번호 → 이름. 범위 밖이면 None."""
    return PRINCIPLES.get(number)


def _number(raw: object) -> int | None:
    """정수·"35"·{"number": 35}·TrizPrinciple → 번호. 그 밖(불리언·소수·글)은 None."""
    if isinstance(raw, TrizPrinciple):
        return raw.number
    if isinstance(raw, dict):
        raw = raw.get("number")
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    return None


def principles(raw: object, *, limit: int = MAX_PRINCIPLES) -> list[TrizPrinciple]:
    """AI·화면이 보낸 원리 목록 → 번호 1~40 만, 이름은 고정 목록으로. 중복 제거, 최대 limit."""
    out: list[TrizPrinciple] = []
    items: Iterable[object] = raw if isinstance(raw, (list, tuple)) else []
    for item in items:
        n = _number(item)
        if n is None or not 1 <= n <= TRIZ_PRINCIPLE_COUNT:
            continue
        if any(p.number == n for p in out):
            continue
        out.append(TrizPrinciple(number=n, name=PRINCIPLES[n]))
        if len(out) >= limit:
            break
    return out
