"""새 과제 추천 갈래 — 새로움 확인·유추 검색 규칙 (ADR 0057,
docs/contracts/novel-recommend.md). 순수 함수.

- 새로움 확인: 넓힌 실시간 검색 뒤 ② 와 같은 규칙 판정을 다시 돌려, 원래 알림에 없던 규칙
  차단 행(`pick_new_alerts`)만 새 유사 과제로 본다. 후보 자료원·차단 기준은 ② 그대로.
- 유추 검색: 아이디어에서 장소·시설·철도 단어를 빼고 '문제' 축 단어만 남긴다
  (`problem_terms`). "철도역사 비둘기 침입 방지" → 비둘기·침입·방지 (철도역사·승강장·철도
  제거). 문제를 일으키는 대상(비둘기)은 남긴다 — 다른 분야(공항·농업·건물)와 공유하는
  문제이기 때문이다.
- 철도 분야 판정(`rail_reason`)은 데이터에 있는 것만 본다: 철도 전용 자료원(사내·공사 자료 등),
  기관 태그(korail·krri·kr — config/sources.yaml institutions), 적재 질의 분야(OpenAlex
  raw.field — sources.yaml 의 철도 분야 질의 목록으로 적재된 문서), 제목·키워드·분류 칸의
  철도 용어, 초록의 강한 철도 용어. 목록은 config/novelty.yaml `rail_field`.
- 분야 이름(`domain_label`)은 자료원 메타데이터(학술지·게재처·과학기술표준분류·소관 부처·
  IPC)에서만, 없으면 자료원 이름. 지어내지 않는다.
- 이유(`why_relevant`)는 공유하는 문제어로 만든 규칙 문장이다(LLM 아님).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rra.domain.models import Document, OverlapAlert, ProposalRequest
from rra.domain.models.live_search import LIVE_SOURCES, LiveSearchConfig, LiveSourceConfig
from rra.domain.rules.keywords import KeywordRule, query_keywords, stem, tokens
from rra.domain.rules.overlap import SOURCE_LABELS

KEY_VERSION = "novelty:v1"
MAX_LABEL_CHARS = 80
MAX_PLACE_PARTS = 4  # "철도역사내" 처럼 붙여 쓴 장소 말 조각 수 상한
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SPACES = re.compile(r"\s+")
_EN_TOKEN = re.compile(r"[a-z][a-z0-9-]*")
_HANGUL = re.compile(r"[가-힣]")

RailReason = Literal["source", "orgs", "corpus_field", "terms", "abstract"]

# 철도 전용 자료원 — 사내 과제·공사 공시·공사 홈페이지·국토부 철도 정책·철도 통계·
# 공사 감사·경영평가.
# 수집 범위가 철도(공사)로 한정된 자료원이다 (config/sources.yaml·각 자료원 yaml).
DEFAULT_RAIL_SOURCES: tuple[str, ...] = (
    "own",
    "alio",
    "korail_web",
    "molit",
    "datago",
    "bai",
    "mofe",
)
# IPC 섹션 (WIPO 국제특허분류 공식 8개 섹션의 국문 이름)
IPC_SECTIONS: dict[str, str] = {
    "A": "생활필수품",
    "B": "처리조작·운수",
    "C": "화학·야금",
    "D": "섬유·지류",
    "E": "고정 구조물",
    "F": "기계공학·조명·가열·무기·폭파",
    "G": "물리학",
    "H": "전기",
}


# ── 설정 ───────────────────────────────────────────────────
class RailFieldRule(BaseModel):
    """같은 분야(철도) 판정 — config/novelty.yaml rail_field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sources: tuple[str, ...] = DEFAULT_RAIL_SOURCES
    orgs: tuple[str, ...] = ("korail", "krri", "kr")
    # raw.field 가 있으면 철도 분야 질의 목록(sources.yaml openalex.queries)으로 적재된 문서
    corpus_field_sources: tuple[str, ...] = ("openalex",)
    # 제목·키워드·과학기술분류·과제명 칸 — 한글은 어절이 이 말로 시작하면, 영문은 낱말이 같으면
    terms_ko: tuple[str, ...] = (
        "철도",
        "열차",
        "전동차",
        "지하철",
        "도시철도",
        "고속철도",
        "광역철도",
        "경전철",
        "궤도",
        "선로",
        "승강장",
        "철도역",
        "전차선",
        "레일",
        "코레일",
        "철도차량",
        "ktx",
        "srt",
    )
    terms_en: tuple[str, ...] = (
        "railway",
        "railways",
        "railroad",
        "railroads",
        "rail",
        "rails",
        "train",
        "trains",
        "metro",
        "subway",
        "tram",
        "tramway",
        "locomotive",
        "locomotives",
        "catenary",
        "pantograph",
        "bogie",
        "ktx",
    )
    # 초록에서는 강한 말만 (초록이 철도를 한 번 언급했다고 철도 문서로 보지 않게 — 강한 말은 예외)
    abstract_terms_ko: tuple[str, ...] = ("철도", "도시철도", "고속철도")
    abstract_terms_en: tuple[str, ...] = ("railway", "railways", "railroad", "railroads")
    abstract_chars: int = Field(default=600, ge=0)


class ProblemAxisRule(BaseModel):
    """'문제' 축 질의 — 장소·시설·철도 단어를 뺀다. config/novelty.yaml analogy.place_terms."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # 한글은 어절이 이 말로 이루어지면(이 말들을 앞에서부터 떼어 남는 것이 없으면) 뺀다
    place_ko: tuple[str, ...] = (
        "철도",
        "철도역",
        "역사",
        "역사내",
        "역",
        "역내",
        "승강장",
        "대합실",
        "선로",
        "궤도",
        "열차",
        "전동차",
        "차량",
        "객차",
        "지하철",
        "도시철도",
        "고속철도",
        "광역철도",
        "터널",
        "교량",
        "차량기지",
        "기지",
        "정거장",
        "플랫폼",
        "코레일",
        "공사",
        "구내",
        "시설",
        "시설물",
        "건물",
        "내부",
        "외부",
        "지붕",
        "천장",
        "ktx",
        "srt",
    )
    place_en: tuple[str, ...] = (
        "railway",
        "railways",
        "railroad",
        "rail",
        "rails",
        "train",
        "trains",
        "station",
        "stations",
        "platform",
        "platforms",
        "subway",
        "metro",
        "track",
        "tracks",
        "tunnel",
        "tunnels",
        "bridge",
        "bridges",
        "depot",
        "facility",
        "facilities",
        "building",
        "buildings",
        "korail",
        "ktx",
        "in",
        "at",
        "of",
        "for",
        "the",
        "a",
        "an",
        "on",
    )
    max_terms: int = Field(default=6, ge=1, le=20)
    max_phrases: int = Field(default=3, ge=1, le=5)


class LiveWidening(BaseModel):
    """넓힌 실시간 검색 — 기존 live_search.yaml 값 위에 덮어쓴다(그 파일은 고치지 않는다)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = True
    max_queries: int = Field(default=5, ge=1, le=5)  # 자료원마다 보낼 키워드 수 (기본 3 → 5)
    per_source_timeout_seconds: float = Field(default=15.0, gt=0, le=60)
    overall_timeout_seconds: float = Field(default=22.0, gt=0, le=120)
    wait_seconds: float = Field(default=25.0, ge=0, le=120)
    sources: dict[str, LiveSourceConfig] = Field(default_factory=dict)  # 비면 기존 값

    def live_config(self, base: LiveSearchConfig) -> LiveSearchConfig:
        """기존 실시간 검색 설정(base)을 넓힌 사본. base 가 꺼져 있으면(가짜 모드 등) 꺼진 채."""
        sources = {name: self.sources.get(name) or base.source(name) for name in LIVE_SOURCES}
        return base.model_copy(
            update={
                "enabled": base.enabled and self.enabled,
                "max_queries": self.max_queries,
                "per_source_timeout_seconds": self.per_source_timeout_seconds,
                "overall_timeout_seconds": self.overall_timeout_seconds,
                "wait_seconds": self.wait_seconds,
                "sources": sources,
            }
        )


class AnalogySettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = True
    max_results: int = Field(default=5, ge=0, le=5)
    search_k: int = Field(default=60, ge=1, le=500)  # 저장 자료에서 받을 후보 수
    # 저장 자료 검색 자료원 (철도 전용 자료원은 어차피 빠지므로 처음부터 뺀다). 비면 전부
    search_sources: tuple[str, ...] = ("scienceon", "openalex", "ntis", "kipris_kr", "kipris_intl")
    # 한글 자료는 문제어가 이만큼 겹쳐야 남긴다 (relevance.min_keyword_hits 와 같은 뜻)
    min_shared_terms: int = Field(default=1, ge=0)
    axis: ProblemAxisRule = Field(default_factory=ProblemAxisRule)
    live: LiveWidening = Field(
        default_factory=lambda: LiveWidening(
            max_queries=3,
            sources={
                "scienceon": LiveSourceConfig(top_n=30, max_requests=8),
                "ntis": LiveSourceConfig(top_n=20, max_requests=6),
                "openalex": LiveSourceConfig(top_n=30, max_requests=3),
            },
        )
    )


class NoveltySettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = True
    live: LiveWidening = Field(default_factory=LiveWidening)


class NoveltyConfig(BaseModel):
    """config/novelty.yaml (ADR 0057). 파일이 없으면 기본값."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    novelty: NoveltySettings = Field(default_factory=NoveltySettings)
    analogy: AnalogySettings = Field(default_factory=AnalogySettings)
    rail_field: RailFieldRule = Field(default_factory=RailFieldRule)
    memo_minutes: float = Field(default=30.0, gt=0)  # 같은 입력 재사용(프로세스 안 LRU)
    memo_size: int = Field(default=64, ge=1, le=5000)


# ── 철도 분야 판정 ─────────────────────────────────────────
def _ko_hit(tok: str, terms: Iterable[str]) -> bool:
    return any(tok.startswith(t) for t in terms)


def _text_tokens(text: str | None) -> list[str]:
    return tokens(unicodedata.normalize("NFKC", text or ""))


def _has_term(text: str | None, ko: Sequence[str], en: Sequence[str]) -> bool:
    if not text:
        return False
    ko_terms = [t.lower() for t in ko]
    en_terms = {t.lower() for t in en}
    for tok in _text_tokens(text):
        if _HANGUL.search(tok):
            if _ko_hit(tok, ko_terms):
                return True
        elif tok in en_terms:
            return True
    return False


def _raw_text(doc: Document, key: str) -> str:
    value = doc.raw.get(key)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(str(v) for v in value if isinstance(v, str))
    return ""


def rail_reason(doc: Document, rule: RailFieldRule) -> RailReason | None:
    """철도 분야 문서면 그 근거, 아니면 None. 데이터(자료원·기관 태그·적재 분야·용어)만 본다."""
    if doc.source in rule.sources:
        return "source"
    if any(o in rule.orgs for o in doc.orgs):
        return "orgs"
    if doc.source in rule.corpus_field_sources and _raw_text(doc, "field").strip():
        return "corpus_field"
    for text in (
        doc.title,
        _raw_text(doc, "keywords"),
        _raw_text(doc, "science_class"),
        _raw_text(doc, "project_title"),
        _raw_text(doc, "journal"),
        _raw_text(doc, "venue"),
    ):
        if _has_term(text, rule.terms_ko, rule.terms_en):
            return "terms"
    if rule.abstract_chars and _has_term(
        (doc.abstract or "")[: rule.abstract_chars], rule.abstract_terms_ko, rule.abstract_terms_en
    ):
        return "abstract"
    return None


# ── '문제' 축 ─────────────────────────────────────────────
def is_place_ko(token: str, axis: ProblemAxisRule) -> bool:
    """어절이 장소·시설·철도 말로만 이루어졌는가 — "철도역사" = 철도 + 역사 → True."""
    places = {p.lower() for p in axis.place_ko if p}

    def split(rest: str, depth: int) -> bool:
        if not rest or rest in places:
            return True
        if depth >= MAX_PLACE_PARTS:
            return False
        return any(
            split(stem(rest[len(p) :]), depth + 1)
            for p in places
            if rest.startswith(p) and len(p) < len(rest)
        )

    return split(stem(token.lower()), 0)


def _strip_phrase_ko(phrase: str, axis: ProblemAxisRule, rule: KeywordRule) -> list[str]:
    words: list[str] = []
    for tok in tokens(phrase):
        if _HANGUL.search(tok):
            if is_place_ko(tok, axis) or tok in rule.generic_terms or len(tok) < 2:
                continue
        elif tok in {p.lower() for p in axis.place_en} or len(tok) < 2:
            continue
        if tok not in words:
            words.append(tok)
    return words


def problem_terms(
    req: ProposalRequest,
    rule: KeywordRule,
    axis: ProblemAxisRule,
    core_keywords: Sequence[str] | None = None,
) -> list[str]:
    """'문제' 축 단어 — 핵심어(있으면 먼저)와 입력(가제·현황·원인·한계·목표)의 고유 키워드에서
    장소·시설·철도 말과 일반어를 뺀 것. 순서 유지, 최대 max_terms."""
    out: list[str] = []
    for kw in core_keywords or ():
        for w in _strip_phrase_ko(kw, axis, rule):
            if _HANGUL.search(w) and w not in out:
                out.append(w)
    text = " ".join(
        p
        for p in (req.title_hint, req.current_state, req.root_cause, req.limitation, req.goal)
        if p
    )
    for tok in query_keywords(text, rule):
        if not _HANGUL.search(tok) or is_place_ko(tok, axis):
            continue
        if any(tok.startswith(t) for t in out):  # "침입해" ← "침입" 이미 있음 (활용형)
            continue
        out.append(tok)
    return out[: axis.max_terms]


def problem_phrases_ko(
    core_keywords: Sequence[str] | None,
    terms: Sequence[str],
    axis: ProblemAxisRule,
    rule: KeywordRule,
) -> list[str]:
    """국문 실시간 검색 질의 — 핵심어 구에서 장소 말을 뺀 것, 모자라면 문제어 두 개 묶음·한 개."""
    out: list[str] = []

    def add(q: str) -> None:
        q = q.strip()
        if q and q not in out:
            out.append(q)

    for kw in core_keywords or ():
        words = [w for w in _strip_phrase_ko(kw, axis, rule) if _HANGUL.search(w)]
        if words:
            add(" ".join(words))
    if len(terms) >= 2:
        add(" ".join(terms[:2]))
    for t in terms:
        add(t)
    return out[: axis.max_phrases]


def problem_phrases_en(en_keywords: Sequence[str] | None, axis: ProblemAxisRule) -> list[str]:
    """영문 실시간 검색 질의 — 영문 키워드에서 장소·철도 낱말을 뺀 것(번역은 하지 않는다)."""
    places = {p.lower() for p in axis.place_en}
    out: list[str] = []
    for kw in en_keywords or ():
        words = [w for w in _EN_TOKEN.findall((kw or "").lower()) if w not in places and len(w) > 1]
        q = " ".join(words)
        if q and q not in out:
            out.append(q)
    return out[: axis.max_phrases]


def en_terms(phrases_en: Sequence[str]) -> list[str]:
    out: list[str] = []
    for q in phrases_en:
        for w in q.split():
            if len(w) >= 3 and w not in out:
                out.append(w)
    return out


def problem_query(terms: Sequence[str], phrases_en: Sequence[str]) -> str:
    """저장 자료 검색(벡터) 질의 — 문제어 + 첫 영문 구."""
    parts = list(terms)
    if phrases_en:
        parts.append(phrases_en[0])
    return " ".join(parts).strip()


def shared_terms(terms: Sequence[str], terms_en: Sequence[str], doc: Document) -> list[str]:
    """문서(제목·초록·키워드)에 나오는 문제어. 한글은 문서 어절이 문제어로 시작하면, 영문은 낱말이
    문제어로 시작하면(복수형·파생형)."""
    text = " ".join(p for p in (doc.title, doc.abstract or "", _raw_text(doc, "keywords")) if p)
    toks = _text_tokens(text)
    out = [t for t in terms if any(d.startswith(t) for d in toks)]
    out += [t for t in terms_en if any(d.startswith(t) for d in toks if not _HANGUL.search(d))]
    return out


# ── 분야 이름·이유 ─────────────────────────────────────────
def clean_label(text: str | None) -> str:
    value = _SPACES.sub(" ", _CONTROL.sub(" ", unicodedata.normalize("NFKC", text or ""))).strip()
    return value[:MAX_LABEL_CHARS]


def domain_label(doc: Document) -> str:
    """자료원 메타데이터의 분야 — 학술지·게재처·과학기술표준분류·소관 부처·IPC.
    없으면 자료원 이름."""
    journal = clean_label(_raw_text(doc, "journal"))
    if journal:
        return f"학술지 {journal}"
    venue = clean_label(_raw_text(doc, "venue"))
    if venue:
        return f"게재처 {venue}"
    science = clean_label(_raw_text(doc, "science_class").split("|", 1)[0])
    if science:
        return f"과학기술표준분류 {science}"
    if doc.doc_type == "patent" and doc.codes:
        code = clean_label(doc.codes[0])[:4]
        section = IPC_SECTIONS.get(code[:1].upper())
        if code and section:
            return f"특허 분류 {code} ({section})"
    ministry = clean_label(_raw_text(doc, "ministry"))
    if ministry:
        return f"소관 부처 {ministry}"
    return SOURCE_LABELS.get(doc.source, doc.source)


def why_relevant(shared: Sequence[str], similarity: float | None) -> str:
    """규칙 문장 — 공유 문제어가 있으면 그것, 없으면 문제 축 질의와의 의미 유사도."""
    if shared:
        return f"철도 밖에서 같은 문제({'·'.join(shared[:4])})를 다룬 자료"
    if similarity is not None:
        return f"철도 밖 자료 — 문제 축 질의와 의미 유사도 {similarity:.2f}"
    return "철도 밖 자료 — 문제 축 질의로 찾음"


# ── 새로움 확인 ───────────────────────────────────────────
def known_ids(alerts: Iterable[OverlapAlert]) -> set[str]:
    out: set[str] = set()
    for a in alerts:
        out.add(a.doc_id)
        out.update(a.merged_ids)
    return out


def pick_new_alerts(
    rows: Iterable[OverlapAlert], original: Iterable[OverlapAlert]
) -> list[OverlapAlert]:
    """넓힌 검색 뒤 규칙 판정 행 중 원래 알림에 없던(묶인 판 포함) 규칙 차단 행. ② 의 차단 기준을
    그대로 쓴다 — 근접(비차단) 행은 새 유사 과제로 보지 않는다."""
    known = known_ids(original)
    out: list[OverlapAlert] = []
    for a in rows:
        blocking = a.rule_blocking if a.rule_blocking is not None else a.blocking
        if not blocking:
            continue
        if a.doc_id in known or known.intersection(a.merged_ids):
            continue
        out.append(a)
        known.add(a.doc_id)
    return out


def _norm(text: str) -> str:
    return _SPACES.sub(" ", unicodedata.normalize("NFKC", text or "").casefold()).strip()


def input_key(req: ProposalRequest, *extra: Iterable[str]) -> str:
    """같은 입력 재사용 키 — 입력 검색 글·정책 근거(live_search.session_key 와 같은 정규화) + 덧붙인
    값(핵심어·원래 알림 doc_id 등)의 sha256. 비밀 없음."""
    parts = [KEY_VERSION, _norm(req.search_text()), _norm(req.policy_basis)]
    for group in extra:
        parts.append("\x1f".join(sorted(_norm(x) for x in group)))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
