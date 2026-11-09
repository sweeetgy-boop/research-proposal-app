"""동의어 후보 선별 규칙 (레인 E, ADR 0059, 계약 docs/contracts/overlap-facets.md §4) — 순수.

입력은 `rra terms candidates` 가 만든 용어 후보 통계(용어·문서빈도·자료원·예시 문서). 두 가지로
묶는다.

- 씨앗 묶음(`SEED_GROUPS`, 철도 용어 사전): 후보에 나타난 구성원이 둘 이상이고 문서빈도가 하한
  이상이면 **high**(고신뢰 — `overlap.yaml synonyms.candidates` 후보 구역에 적는다). 하나만
  나타나면 review. 관련어 묶음(`LOOSE_GROUPS`: 선로/궤도/레일, 도상/자갈도상 …)은 review 까지만.
- 포함 관계(한 용어가 다른 용어를 품음: 철도교량/교량, 자갈도상/도상)이고 예시 문서가 겹치면(공출현
≥
  하한) **review** — 상·하위어일 수 있어 사람이 본다.

일반어(KeywordRule.generic_terms)·기록 서식어는 구성원에서 뺀다. 결과는
검토표(`docs/review/terms-review.md`)
로만 간다 — 운영 스위치 `synonyms.enabled` 는 사람 검토 뒤에만 켠다. 질의 확장은 OR(FTS5 토큰별
인용),
차단 키워드 겹침에는 쓰지 않는다(1단계).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rra.domain.rules.keywords import KeywordRule, stem

Confidence = Literal["high", "review"]

# 대표어 먼저. 어간(조사 제거) 기준으로 비교한다 — "고속철도" 는 stem 에서 "고속철" 이 된다.
SEED_GROUPS: tuple[tuple[str, ...], ...] = (
    ("유지보수", "유지관리", "보수"),
    ("전차선", "가선", "전차선로", "전차선설비"),
    ("궤도틀림", "궤도불규칙", "궤도이상", "궤도변위", "궤도검측"),
    ("고속철도", "고속철", "고속열차", "ktx", "경부고속철", "경부고속철도"),
    ("승강장", "플랫폼", "타는곳"),
    ("분기기", "턴아웃", "선로전환기"),
    ("침목", "슬리퍼", "pc침목"),
    ("차륜", "바퀴", "휠"),
    ("차량기지", "기지", "검수고"),
    ("신호설비", "신호시스템", "신호기"),
    ("정거장", "역사", "역건물"),
    ("수송수요", "수요예측"),
)
# 뜻이 가깝지만 같은 말은 아닌 묶음(상·하위어·관련어) — 후보에 다 나타나도 review 까지만 (사람 판단)
LOOSE_GROUPS: tuple[tuple[str, ...], ...] = (
    ("도상", "자갈도상", "콘크리트도상"),
    ("선로", "궤도", "레일", "철도궤도"),
    ("철도차량", "열차", "차량"),
    ("검측", "검사", "점검"),
    ("수송수요", "수송실적"),
)
# 어미로 끝나는 서술형 토큰(분석하였다·이용하여 …)은 용어가 아니다 — 묶음 구성원에서 뺀다
_VERBAL_ENDINGS: tuple[str, ...] = (
    "다",
    "여",
    "고",
    "며",
    "서",
    "면",
    "음",
    "함",
    "된",
    "한",
    "하",
    "됨",
)
_RECORD_FORM_WORDS: frozenset[str] = frozenset(
    {
        "과제명",
        "과제목록",
        "총연구비",
        "경영연구처",
        "기술연구처",
        "연구내용",
        "연구목적",
        "기대효",
        "활용계획",
    }
)


class TermStatRow(BaseModel):
    """후보 통계 한 줄 (candidates yaml 의 행)."""

    model_config = ConfigDict(frozen=True)

    term: str
    doc_freq: int = 0
    sources: dict[str, int] = Field(default_factory=dict)
    examples: tuple[str, ...] = ()
    kind: Literal["rail", "generic"] = "rail"


class SynonymConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_doc_freq: int = Field(default=5, ge=1)  # 구성원 문서빈도 하한
    min_cooccur: int = Field(default=1, ge=0)  # 포함 관계 묶음의 예시 문서 겹침 하한
    min_contain_extra: int = Field(default=2, ge=1)  # 포함 관계: 긴 쪽이 몇 글자 더 길어야 하나


class SynonymReview(BaseModel):
    """검토표 한 줄."""

    model_config = ConfigDict(frozen=True)

    canonical: str
    variants: tuple[str, ...]  # 후보에 실제로 나타난 구성원(대표어 포함, 빈도 순)
    doc_freq: int  # 구성원 문서빈도 합
    cooccur: int  # 예시 문서 겹침 수(공출현 근거)
    confidence: Confidence
    basis: Literal["seed", "related", "contains"]  # 씨앗 동의어 · 관련어 묶음 · 포함 관계
    missing: tuple[str, ...] = ()  # 씨앗 묶음 중 후보에 없던 구성원


def _norm(term: str) -> str:
    return stem(term.strip().lower())


def _is_term(norm: str) -> bool:
    return len(norm) >= 2 and not norm.endswith(_VERBAL_ENDINGS)


def _cooccur(rows: Sequence[TermStatRow]) -> int:
    seen: dict[str, int] = {}
    for r in rows:
        for e in set(r.examples):
            seen[e] = seen.get(e, 0) + 1
    return sum(1 for c in seen.values() if c >= 2)


def select_synonyms(
    rows: Iterable[TermStatRow], rule: KeywordRule, config: SynonymConfig | None = None
) -> list[SynonymReview]:
    """후보 통계 → 검토 줄 (high 먼저, 그 안에서 문서빈도 합 내림차순)."""
    config = config or SynonymConfig()
    generic = {_norm(t) for t in rule.generic_terms}
    by_norm: dict[str, TermStatRow] = {}
    for r in rows:
        n = _norm(r.term)
        if not _is_term(n) or n in generic or n in _RECORD_FORM_WORDS or r.kind == "generic":
            continue
        if n not in by_norm or r.doc_freq > by_norm[n].doc_freq:
            by_norm[n] = r
    out: list[SynonymReview] = []
    used: set[str] = set()
    for group, loose in [(g, False) for g in SEED_GROUPS] + [(g, True) for g in LOOSE_GROUPS]:
        # "전차선로"→"전차선" 같은 어간 중복 제거
        norms = list(dict.fromkeys(_norm(g) for g in group))
        present = [by_norm[n] for n in norms if n in by_norm and n not in generic and n not in used]
        if not present:
            continue
        strong = [r for r in present if r.doc_freq >= config.min_doc_freq]
        confidence: Confidence = "high" if len(strong) >= 2 and not loose else "review"
        present.sort(key=lambda r: -r.doc_freq)
        used.update(_norm(r.term) for r in present)
        out.append(
            SynonymReview(
                canonical=group[0],
                variants=tuple(r.term for r in present),
                doc_freq=sum(r.doc_freq for r in present),
                cooccur=_cooccur(present),
                confidence=confidence,
                basis="related" if loose else "seed",
                missing=tuple(g for g in group if _norm(g) not in by_norm),
            )
        )
    # 포함 관계 — 씨앗에 안 든 것만, review
    terms = sorted(n for n in by_norm if n not in used)
    for short in terms:
        if len(short) < 2:
            continue
        longer = [
            by_norm[t]
            for t in terms
            if t != short and short in t and len(t) - len(short) >= config.min_contain_extra
        ]
        if not longer:
            continue
        members = [by_norm[short], *longer]
        co = _cooccur(members)
        if co < config.min_cooccur:
            continue
        if any(r.doc_freq < config.min_doc_freq for r in members[:2]):
            continue
        members.sort(key=lambda r: -r.doc_freq)
        out.append(
            SynonymReview(
                canonical=by_norm[short].term,
                variants=tuple(r.term for r in members),
                doc_freq=sum(r.doc_freq for r in members),
                cooccur=co,
                confidence="review",
                basis="contains",
            )
        )
    out.sort(key=lambda s: (s.confidence != "high", -s.doc_freq, s.canonical))
    return out


def high_confidence(reviews: Sequence[SynonymReview]) -> list[SynonymReview]:
    return [r for r in reviews if r.confidence == "high"]


def expand_terms(terms: Sequence[str], groups: Iterable[Sequence[str]]) -> list[str]:
    """질의 토큰 OR 확장 — 토큰이 든 묶음의 다른 구성원을 뒤에 더한다(순서 유지·중복 없음). 차단
    키워드 겹침에는 쓰지 않는다(1단계). 스위치 `synonyms.enabled` 가 켜졌을 때만 호출된다."""
    table: dict[str, tuple[str, ...]] = {}
    for g in groups:
        members = tuple(dict.fromkeys(m for m in g if m))
        for m in members:
            table.setdefault(_norm(m), members)
    out: list[str] = []
    for t in terms:
        if t not in out:
            out.append(t)
        for m in table.get(_norm(t), ()):
            if m not in out:
                out.append(m)
    return out
