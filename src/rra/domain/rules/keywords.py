"""유사과제 판정의 두 번째 근거 — 질의와 문서가 실제로 공유하는 키워드.

multilingual-e5 의 코사인은 분포가 압축돼 서로 무관한 한국어 문장도 0.79~0.83 이 나온다.
own 임계치 0.80 이 그 바닥에 걸려 있어, 유사도만으로 차단하면 주제가 전혀 다른 제안도 차단된다.
그래서 차단에는 "질의의 고유 키워드가 문서에도 등장한다"는 조건을 함께 요구한다 (`overlap.judge`).

토큰화는 FTS5 unicode61 과 같은 어절 단위(공백·구두점 분리, 형태소 분석 없음)다. 한국어 조사가
붙으면 "자산개발을"·"자산개발의"·"자산개발" 이 다른 토큰이 되므로, 양쪽 토큰의 끝 조사를 떼고
(`stem`) FTS 접두 질의처럼 "문서 토큰이 질의 어간으로 시작하면" 일치로 본다.
철도 문서에 흔한 일반어(철도·개선·연구…)는 세지 않는다 (`KeywordRule.generic_terms`,
config/overlap.yaml 로 보충).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

# FTS5 unicode61 과 같은 경계: 문자·숫자 묶음. 밑줄은 별도로 뺀다.
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_NUMERIC = re.compile(r"\A\d+\Z")
MIN_STEM_CHARS = 2

# 어절 끝에서 떼는 조사. 긴 것부터 시도하고, 떼고 나서 2자 이상 남을 때만 뗀다.
# 한 글자 어미(다·고·라…)는 "평가·비교·참고" 같은 명사를 깨므로 두 글자 조합으로만 다룬다.
PARTICLES: tuple[str, ...] = tuple(
    sorted(
        {
            "에서는",
            "으로서",
            "으로써",
            "에게는",
            "에서",
            "에는",
            "에도",
            "에만",
            "으로",
            "로서",
            "로써",
            "이며",
            "이고",
            "이다",
            "입니다",
            "처럼",
            "보다",
            "부터",
            "까지",
            "과의",
            "와의",
            "이란",
            "에게",
            "은",
            "는",
            "이",
            "가",
            "을",
            "를",
            "의",
            "에",
            "도",
            "와",
            "과",
            "로",
            "만",
            "며",
        },
        key=len,
        reverse=True,
    )
)

# 철도 과제 문서라면 어디에나 있는 말 — 겹쳐도 같은 과제라는 근거가 되지 않는다.
DEFAULT_GENERIC_TERMS: frozenset[str] = frozenset(
    {
        "철도",
        "코레일",
        "한국철도공사",
        "공사",
        "철도공사",
        "철도연구원",
        "개선",
        "연구",
        "분석",
        "시스템",
        "방안",
        "기술",
        "개발",
        "과제",
        "제안",
        "사업",
        "현황",
        "적용",
        "활용",
        "구축",
        "수립",
        "방법",
        "체계",
        "관리",
        "효과",
        "결과",
        "필요",
        "현재",
        "기존",
        "대상",
        "운영",
        "추진",
        "마련",
        "검토",
        "향상",
        "강화",
        "확보",
        "문제",
        "요구",
        "한계",
        "목표",
        "기반",
        "제시",
        "조사",
        "모델",
        "계획",
        "통해",
        "위해",
        "위한",
        "따른",
        "대한",
        "관련",
        "주요",
        "등",
        "및",
        "방식",
        "단순",
        "다양한",
        "있다",
        "없다",
        "된다",
        "한다",
    }
)


class KeywordRule(BaseModel):
    """차단 조건: 일반어를 뺀 질의 키워드가 문서에 `min_hits` 개 이상 등장."""

    model_config = ConfigDict(frozen=True)

    min_hits: int = Field(default=2, ge=1)
    generic_terms: frozenset[str] = DEFAULT_GENERIC_TERMS

    def with_extra_generic(self, terms: list[str] | tuple[str, ...]) -> KeywordRule:
        extra = {stem(t.strip().lower()) for t in terms if t and t.strip()}
        return self.model_copy(update={"generic_terms": self.generic_terms | extra})


def stem(token: str) -> str:
    """끝 조사를 최대 두 번 뗀다. 떼고 2자 미만이 되면 떼지 않는다."""
    for _ in range(2):
        for p in PARTICLES:
            if token.endswith(p) and len(token) - len(p) >= MIN_STEM_CHARS:
                token = token[: -len(p)]
                break
        else:
            break
    return token


def tokens(text: str) -> list[str]:
    """어절 → 소문자 → 조사 제거. 순서 유지, 중복 제거."""
    out: list[str] = []
    for tok in _TOKEN_RE.findall(text or ""):
        s = stem(tok.lower())
        if s not in out:
            out.append(s)
    return out


def query_keywords(query: str, rule: KeywordRule) -> list[str]:
    """질의에서 셀 만한 키워드: 2자 이상, 숫자 아님, 일반어 아님."""
    return [
        t
        for t in tokens(query)
        if len(t) >= MIN_STEM_CHARS and not _NUMERIC.match(t) and t not in rule.generic_terms
    ]


def keyword_overlap(query: str, doc_text: str, rule: KeywordRule) -> list[str]:
    """질의 키워드 중 문서에 등장하는 것. FTS5 접두 질의처럼 문서 토큰이 질의 어간으로 시작하면
    일치다 ("자산개발" ↔ "자산개발을·자산개발사업"). 질의 길이가 상한(500자)이라 개수도 유한하다."""
    doc_tokens = tokens(doc_text)
    return [kw for kw in query_keywords(query, rule) if any(d.startswith(kw) for d in doc_tokens)]


def enough(hits: list[str], rule: KeywordRule) -> bool:
    return len(hits) >= rule.min_hits
