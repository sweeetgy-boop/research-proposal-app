"""입력 근거 규칙 — 정책·계획명, 차수·연도를 지어내지 못하게 한다.

정책적 중요도(2-가-(1))는 수집 자료에 정책 문서가 없어 제안자 입력만 근거로 쓴다.
프롬프트로 금지하는 데 더해, 문장에서 고유명처럼 보이는 표현을 뽑아 허용 텍스트(제안자 입력,
전략 목록)에 있는지 대조한다. 없으면 그 문장을 폐기한다.

뽑는 대상 (보수적으로 — 놓치는 것보다 과하게 버리는 쪽):
- 「」·『』·“”·"" 안의 표현
- `…계획`·`…전략`·`…정책`·`…로드맵`·`…규정`·`…지침`·`…비전`·`…법률`·`…시행령` 으로 끝나는 어절
  (뒤에는 조사만 허용. "정책적·계획적으로" 같은 파생어는 고유명이 아니다.
  앞에 한 글자 이상 붙은 경우. 일반어는 GENERIC_TERMS 로 허용)
- 바로 앞 어절이 관형형(~한·~된·~는·~적인·~운: "중요한 정책", "새로운 계획")이면 이름을 이루지
  않는다 → 뒤의 일반어("정책")만 남고 그것은 _BARE 로 허용된다
- 두 자리 이상 숫자 (연도·차수·목표치)

대조는 공백을 없앤 부분 문자열 비교다.
한계: 허용 텍스트에 있는 이름을 다른 뜻으로 쓰는 것은 막지 못한다. 일반어("유지보수 계획")도
입력에 없으면 버려진다 — 과하게 버리는 쪽을 택했다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_SUFFIX = r"(?:기본계획|계획|전략|정책|로드맵|규정|지침|비전|법률|시행령|시행규칙)"
_W = r"[가-힣A-Za-z0-9·\-]"
# 어절 뒤에 붙을 수 있는 조사. "계획적·정책적·계획안" 처럼 접미사 뒤에 다른 말이 오면
# 고유명이 아니다.
_PARTICLE = (
    r"(?:은|는|이|가|을|를|의|에|에서|에는|에도|에만|도|와|과|와의|과의|로|으로|로서|으로서|로써|으로써"
    r"|로의|으로의|만|부터|까지|처럼|보다|이며|며|이고|고|이다|다|입니다|이라|라|인|이란|란|임|이자)"
)
_TERM = re.compile(rf"\A({_W}*?{_SUFFIX}){_PARTICLE}{{0,2}}\Z")  # 접미사로 끝나는 어절(조사 허용)
_BARE = re.compile(rf"\A{_SUFFIX}\Z")
_QUOTED = re.compile(r"「([^」]{1,80})」|『([^』]{1,80})』|“([^”]{1,80})”|\"([^\"]{1,80})\"")
_NUMBER = re.compile(r"제\s?\d+\s?차|\d{2,}")
_PUNCT = "()[]{}<>,.;:!?'\"「」『』“”‘’·"
_PARTICLE_END = set("은는이가을를의에도와과로서및며고")
# 관형형 어미 — "중요한·필요한·관련된·새로운·정책적인 + 계획" 은 고유명이 아니다
_ADJECTIVE_END = ("한", "된", "는", "적인", "운")

# 고유명이 아닌 일반어 — 입력에 없어도 허용
GENERIC_TERMS: frozenset[str] = frozenset(
    {
        "경영전략",
        "대응전략",
        "추진전략",
        "사업계획",
        "세부계획",
        "실행계획",
        "추진계획",
        "연구계획",
        "활용계획",
        "실용화계획",
        "업무계획",
        "주요업무계획",
        "중장기계획",
        "관련규정",
        "내부규정",
        "관련정책",
        "정부정책",
    }
)

# 이름을 이루지 않는 수식어 — "관련 계획", "해당 규정" 은 고유명이 아니다
GENERIC_MODIFIERS: frozenset[str] = frozenset(
    {"관련", "해당", "본", "이", "그", "각", "세부", "향후", "기존", "신규", "별도", "내부", "정부"}
)


def _squash(text: str) -> str:
    return "".join(text.split())


def named_references(text: str) -> list[str]:
    """문장에서 입력 근거가 필요한 표현을 뽑는다 (순서 유지, 중복 제거).

    `…계획` 류 어절은 바로 앞 어절이 수식어(조사로 끝나지 않는 말)이면 함께 뽑는다:
    "국가철도망 구축계획" → 두 어절이 붙어서 입력에 있어야 한다. "정부의 구축계획" → "구축계획"만.
    """
    found: list[str] = []
    for m in _QUOTED.finditer(text):
        found.append(next(g for g in m.groups() if g))
    words = [w.strip(_PUNCT) for w in text.split()]
    for i, word in enumerate(words):
        m = _TERM.match(word)
        if m is None:
            continue
        term = m.group(1)
        prev = words[i - 1] if i > 0 else ""
        name_like = (
            prev
            and prev[-1] not in _PARTICLE_END
            and prev not in GENERIC_MODIFIERS
            and not prev.endswith(_ADJECTIVE_END)
        )
        if name_like and not _NUMBER.fullmatch(prev):
            found.append(f"{prev} {term}")
        elif not _BARE.match(term) and term not in GENERIC_TERMS:
            found.append(term)
    found.extend(_NUMBER.findall(text))
    out: list[str] = []
    for f in found:
        f = f.strip()
        if f and f not in out:
            out.append(f)
    return out


def ungrounded(text: str, allowed_texts: Iterable[str]) -> list[str]:
    """허용 텍스트 어디에도 없는 표현. 비어 있으면 통과."""
    haystack = _squash(" ".join(allowed_texts))
    return [ref for ref in named_references(text) if _squash(ref) not in haystack]
