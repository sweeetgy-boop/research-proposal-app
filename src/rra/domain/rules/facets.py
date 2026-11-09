"""② 4축 분해 규칙 (레인 E, ADR 0059, 계약 docs/contracts/overlap-facets.md §2) — 순수.

아이디어를 target(대상)·problem(문제)·method(방법)·place(장소) 로 나눈다. 두 길이 있다.

- 로컬 모델 출력 파서 `parse_facets`: JSON 객체 하나(`{"facets": {...}}` 또는 네 키가 바로 있는
것)만
  받고, 네 축이 모두 문자열이고 한 줄 80자 이하일 때만 `Facets(source=local)`. 그 밖은 None → 규칙.
- 규칙 분해 `split_by_rule`: 핵심어(Argon 키워드 → 없으면 질의 키워드)를 축 사전으로 배정한다 —
  장소(역·구간·지역·노선 이름), 방법(기술·기법·장치·시스템·분석·모형·센서 …), 대상(시설·차량·설비·
  업무 명사), 그 밖은 problem. 문제 어근(틀림·균열·장애·오염 …)이 든 복합어는 problem 이 먼저다
  ("궤도틀림" → problem, "궤도" → target).

검색용 `facet_queries` 는 비어 있지 않은 축 값 — 2개 이상일 때만 축별 검색을 한다(1개면 한 질의와
다를 게 없다). 어떤 축도 차단을 바꾸지 않는다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from rra.domain.models.facets import FACET_KEYS, MAX_FACET_CHARS, Facets
from rra.domain.rules.keywords import KeywordRule, core_terms, query_keywords

MIN_FACET_QUERIES = 2
MAX_FACET_QUERIES = 4
MAX_RULE_TERMS = 12  # 규칙 분해에 쓰는 핵심어 수 상한 (질의 전체 토큰일 때)

# ── 축 사전 (어간 토큰 기준; 포함 일치) ──────────────────────
PROBLEM_ROOTS: tuple[str, ...] = (
    "틀림",
    "균열",
    "장애",
    "오염",
    "침입",
    "점유",
    "민원",
    "지연",
    "사고",
    "고장",
    "마모",
    "파손",
    "탈선",
    "소음",
    "진동",
    "아크",
    "누수",
    "부식",
    "결함",
    "손상",
    "혼잡",
    "오차",
    "방치",
    "유휴",
    "낭비",
    "과열",
    "피로",
    "열화",
    "침하",
    "변형",
    "불량",
    "부족",
    "누락",
    "중복",
)
PLACE_WORDS: frozenset[str] = frozenset(
    {
        "수도권",
        "지상역",
        "지하역",
        "본선",
        "경부선",
        "호남선",
        "중앙선",
        "경의선",
        "경춘선",
        "경인선",
        "전라선",
        "장항선",
        "충북선",
        "동해선",
        "경전선",
        "태백선",
        "영동선",
        "수인선",
        "분당선",
        "도심",
        "역세권",
        "신설역",
        "환승역",
        "종착역",
        "폐역",
        "시범역",
        "광역권",
        "지방",
        "농어촌",
        "도서",
        "해안",
        "산악",
        "국경",
        "경부고속선",
        "호남고속선",
        "경강선",
        "고속선",
        "일반선",
    }
)
PLACE_SUFFIXES: tuple[str, ...] = ("구간", "지역", "권역", "지점", "일대", "관내", "구내")
METHOD_ROOTS: tuple[str, ...] = (
    "기술",
    "기법",
    "장치",
    "시스템",
    "분석",
    "모형",
    "모델",
    "알고리즘",
    "센서",
    "감지",
    "진단",
    "예측",
    "추정",
    "판독",
    "학습",
    "제어",
    "설계",
    "측정",
    "검측",
    "모니터링",
    "퇴치",
    "보정",
    "계측",
    "딥러닝",
    "인공지능",
    "드론",
    "영상",
    "초음파",
    "레이저",
    "데이터",
    "플랫폼",
    "자동화",
    "최적화",
    "시뮬레이션",
    "해석",
    "평가",
    "지표",
    "매뉴얼",
    "가이드라인",
    "조명",
    "통신",
    "무선",
    "lte",
    "iot",
    "rfid",
    "gps",
    "ai",
    "bim",
    "gis",
    "연계",
    "연동",
    "점검",
    "탐지",
    "인식",
    "방호",
    "복합",
)
TARGET_ROOTS: tuple[str, ...] = (
    "차량",
    "설비",
    "시설",
    "베어링",
    "차축",
    "궤도",
    "전차선",
    "가선",
    "도상",
    "레일",
    "침목",
    "분기기",
    "신호기",
    "캐노피",
    "승강장",
    "역사",
    "부지",
    "차량기지",
    "변전소",
    "급전",
    "열차",
    "화차",
    "객차",
    "기관차",
    "대차",
    "제동",
    "팬터그래프",
    "터널",
    "교량",
    "노반",
    "건널목",
    "주차장",
    "좌석",
    "엘리베이터",
    "에스컬레이터",
    "공간",
    "도서관",
    "수요",
    "에너지",
    "비둘기",
    "조류",
    "동물",
    "승객",
    "이용객",
    "직원",
    "인력",
    "자산",
    "자재",
    "부품",
    "선로",
    "역무",
    "화물",
    "여객",
    "운임",
    "요금",
    "예약",
    "출입구",
    "스크린도어",
    "배선",
    "케이블",
    "전력",
    "조명등",
    "구조물",
    "건축물",
    "차륜",
    "휠",
    "윤축",
    "모터",
    "인버터",
    "배터리",
    "축전지",
    "냉난방",
    "공조",
    "토공",
    "사면",
    "배수",
    "울타리",
    "방음벽",
)
_PLACE_EXCLUDE: frozenset[str] = frozenset({"영역", "구역", "역할", "역량", "역사", "역무", "역시"})


def _has_root(token: str, roots: Sequence[str]) -> bool:
    return any(r in token for r in roots)


def facet_of(token: str) -> str:
    """어간 토큰 하나의 축. 문제 → 장소 → 방법 → 대상 → (그 밖) 문제."""
    t = token.lower()
    if _has_root(t, PROBLEM_ROOTS):
        return "problem"
    if t in PLACE_WORDS or t.endswith(PLACE_SUFFIXES):
        return "place"
    if t.endswith("역") and len(t) >= 3 and t not in _PLACE_EXCLUDE:
        return "place"
    if _has_root(t, METHOD_ROOTS):
        return "method"
    if _has_root(t, TARGET_ROOTS):
        return "target"
    return "problem"


def split_by_rule(query: str, core_keywords: Sequence[str] | None, rule: KeywordRule) -> Facets:
    """핵심어(없으면 질의 키워드 상위 MAX_RULE_TERMS)를 축에 배정한 규칙 분해. 아무 토큰도 없으면
    source=none 빈 모델."""
    terms = core_terms(list(core_keywords or []), rule) if core_keywords else []
    if not terms:
        terms = query_keywords(query or "", rule)[:MAX_RULE_TERMS]
    if not terms:
        return Facets()
    buckets: dict[str, list[str]] = {k: [] for k in FACET_KEYS}
    for t in terms:
        buckets[facet_of(t)].append(t)
    return Facets(source="rule", **{k: " ".join(v) for k, v in buckets.items()})


def parse_facets(data: Mapping[str, Any] | None) -> Facets | None:
    """로컬 모델 JSON → Facets(local). 네 축이 모두 문자열(비어도 됨)·한 줄 80자 이하가 아니면 None.
    여분 키는 무시한다(비신뢰 출력 — 값은 글자만 쓴다)."""
    if not isinstance(data, Mapping):
        return None
    inner = data.get("facets") if isinstance(data.get("facets"), Mapping) else data
    values: dict[str, str] = {}
    for key in FACET_KEYS:
        v = inner.get(key) if isinstance(inner, Mapping) else None
        if not isinstance(v, str):
            return None
        text = " ".join(v.split())
        if len(text) > MAX_FACET_CHARS:
            return None
        values[key] = text
    if not any(values.values()):
        return None
    return Facets(source="local", **values)


def facet_queries(facets: Facets | None) -> list[str]:
    """축별 검색 질의 — 비어 있지 않은 축 값(순서 target·problem·method·place), 2개 미만이면 []."""
    if facets is None:
        return []
    out = [v for v in (getattr(facets, k) for k in FACET_KEYS) if v]
    if len(out) < MIN_FACET_QUERIES:
        return []
    return out[:MAX_FACET_QUERIES]
