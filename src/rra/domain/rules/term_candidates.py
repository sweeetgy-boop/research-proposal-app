"""용어 후보 추출 규칙 — 순수 (P2-9, architecture §5-7 "용어사전 반자동 확장").

코퍼스 표본(청크 본문)에서 두 종류의 후보를 문서빈도 통계로 뽑는다. **후보일 뿐이다** —
`config/overlap.yaml generic_terms` 나 철도 용어 목록에 자동 반영하지 않는다(오염 위험, 승인은
사람).

- 토큰: `keywords.tokens`(FTS5 unicode61 과 같은 어절 분리 + 조사 제거) 중 한글 2~8자만.
  영어 논문의 라틴 토큰·숫자·혼합 표기는 세지 않는다(일반어 목록도 한글이다).
- 문서빈도 df = 그 토큰이 든 문서(doc_id) 수, 자료원 분포 = 그 문서들의 source 별 수.
- 흔한 단어 후보: df/문서수 ≥ `generic_doc_ratio` 이고 자료원 ≥ `generic_min_sources`(표본 자료원
  수보다 크면 그 수). 이미 일반어(기본 + overlap.yaml)인 것은 뺀다.
- 철도 용어 후보: df ≥ `min_doc_freq` 이고 흔한 단어 조건에 걸리지 않는 것. 철도 어근
  (`RAIL_SEEDS`: 궤도·전차·분기·신호…)이 들어 있으면 hint=rail_seed 로 표시하고 앞세운다.
  점수 = df × (2 if hint else 1). 표시일 뿐 조건이 아니다 — 사람이 보고 고른다.
- 예시 doc_id 는 후보마다 최대 `examples` 개(먼저 나온 순).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from rra.domain.rules.keywords import KeywordRule, stem, tokens

_HANGUL = re.compile(r"^[가-힣]+$")
RAIL_SEEDS: tuple[str, ...] = (
    "철도",
    "궤도",
    "전차",
    "열차",
    "차량",
    "신호",
    "선로",
    "레일",
    "분기",
    "전철",
    "승강장",
    "침목",
    "도상",
    "변전",
    "급전",
    "기관차",
    "객차",
    "화차",
    "동력",
    "대차",
    "제동",
    "운전",
    "역무",
    "운행",
    "고속",
    "터널",
    "교량",
    "노반",
    "궤간",
    "관제",
    "역사",
    "선구",
    "건널목",
    "차륜",
    "팬터",
    "가선",
    "장대",
    "체결",
    "탈선",
    "검측",
    "유지보수",
    "역세권",
    "수송",
    "여객",
    "화물",
    "철도역",
)


class CandidateConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_chars: int = Field(default=2, ge=1)
    max_chars: int = Field(default=8, ge=2)
    min_doc_freq: int = Field(default=3, ge=1)
    generic_doc_ratio: float = Field(default=0.15, gt=0.0, le=1.0)
    generic_min_sources: int = Field(default=2, ge=1)
    examples: int = Field(default=3, ge=1, le=10)
    limit: int = Field(default=200, ge=1, le=5000)


@dataclass(frozen=True)
class CorpusText:
    """표본 한 건 — 청크 본문. source 는 Document.source (doc_id 접두어와 같다)."""

    doc_id: str
    source: str
    text: str


class TermStat(BaseModel):
    model_config = ConfigDict(frozen=True)

    term: str
    doc_freq: int
    chunk_freq: int
    doc_ratio: float
    sources: dict[str, int]
    examples: list[str]
    hint: str | None = None
    score: float = 0.0


class CandidateReport(BaseModel):
    documents: int
    chunks: int
    sources: dict[str, int]  # 표본의 자료원별 문서 수
    rail: list[TermStat]
    generic: list[TermStat]


def _eligible(token: str, config: CandidateConfig) -> bool:
    return config.min_chars <= len(token) <= config.max_chars and bool(_HANGUL.match(token))


def rail_hint(term: str) -> str | None:
    return "rail_seed" if any(seed in term for seed in RAIL_SEEDS) else None


def term_candidates(
    texts: Iterable[CorpusText], rule: KeywordRule, config: CandidateConfig | None = None
) -> CandidateReport:
    config = config or CandidateConfig()
    docs_of: dict[str, set[str]] = defaultdict(set)
    chunk_freq: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    doc_source: dict[str, str] = {}
    n_chunks = 0
    for item in texts:
        n_chunks += 1
        doc_source.setdefault(item.doc_id, item.source)
        for tok in tokens(item.text):
            if not _eligible(tok, config):
                continue
            chunk_freq[tok] += 1
            docs_of[tok].add(item.doc_id)
            ex = examples[tok]
            if item.doc_id not in ex and len(ex) < config.examples:
                ex.append(item.doc_id)
    n_docs = len(doc_source)
    source_counts = Counter(doc_source.values())
    generic_known = {stem(t) for t in rule.generic_terms} | set(rule.generic_terms)
    min_sources = min(config.generic_min_sources, max(1, len(source_counts)))
    rail: list[TermStat] = []
    generic: list[TermStat] = []
    for term, docs in docs_of.items():
        if term in generic_known or stem(term) in generic_known:
            continue
        df = len(docs)
        if df < config.min_doc_freq and n_docs >= config.min_doc_freq:
            continue
        ratio = df / n_docs if n_docs else 0.0
        sources = Counter(doc_source[d] for d in docs)
        hint = rail_hint(term)
        stat = TermStat(
            term=term,
            doc_freq=df,
            chunk_freq=chunk_freq[term],
            doc_ratio=round(ratio, 4),
            sources=dict(sorted(sources.items())),
            examples=list(examples[term]),
            hint=hint,
            score=float(df * (2 if hint else 1)),
        )
        if ratio >= config.generic_doc_ratio and len(sources) >= min_sources:
            generic.append(stat)
        else:
            rail.append(stat)
    rail.sort(key=lambda s: (-s.score, -s.doc_freq, s.term))
    generic.sort(key=lambda s: (-s.doc_freq, s.term))
    return CandidateReport(
        documents=n_docs,
        chunks=n_chunks,
        sources=dict(sorted(source_counts.items())),
        rail=rail[: config.limit],
        generic=generic[: config.limit],
    )
