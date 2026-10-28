"""[4] 실시간 자료 검색 규칙 — 순수 함수 (ADR 0031).

- 키워드: LLM(Argon → 로컬) JSON 을 검증·정리하고(문자열만, 길이·개수 상한, 개인정보 제거, 검색
연산자
  제거), 모자라면 규칙 기반(keywords.py 토큰)으로 채운다. 정책명·고유명사는 고치지 않는다 — LLM 에게
  원문 그대로 쓰라고 지시하고, 여기서는 글자를 바꾸지 않고 거르기만 한다.
- 질의: 키워드 앞 둘을 AND(공백)로 먼저, 결과가 모자라면 첫째·둘째 키워드 하나씩
  (ScienceON 공백 = AND, `|` = OR — sources.yaml 주석, 2026-10-28 실호출 확인).
- 캐시 키: 자료원 + 정규화한 질의 목록 + 건수의 sha256 (비밀 없음, 보안 C).
- 세션 키: 소유자 키 + 입력 검색 글의 sha256 — 같은 입력으로 run 을 만들면 그 세션을 이어 쓴다.
- 저장 전 정리: 사람 이름 제거(authors 비움, 본문 개인정보 표식), visibility public, raw.live=true,
  raw.live_first_seen=세션 해시.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from rra.domain.models import Document, ProposalRequest
from rra.domain.models.live_search import (
    MAX_KEYWORDS,
    MIN_KEYWORDS,
    KeywordOrigin,
    LiveKeywords,
    LiveSourceResult,
    LiveStatus,
)
from rra.domain.rules.dedup import identity_key
from rra.domain.rules.keywords import KeywordRule, query_keywords
from rra.domain.rules.privacy import strip_personal

MAX_KEYWORD_CHARS = 40
MAX_INPUT_CHARS = 1500  # 키워드 LLM 에 보내는 입력 상한
MAX_QUERIES = 3
CACHE_VERSION = "live:v1"
SESSION_HASH_CHARS = 12

_HANGUL = re.compile(r"[가-힣]")
_LATIN = re.compile(r"[A-Za-z]")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
# 검색 연산자·따옴표·괄호 등은 지운다 (ScienceON `|`·`!`, OpenAlex OR/NOT·따옴표). 남기는 것:
# 글자·숫자·
# 공백·하이픈·가운뎃점·마침표·슬래시·앰퍼샌드·플러스
_DISALLOWED = re.compile(r"[^\w\s\-·./&+]", re.UNICODE)
_OPERATORS = re.compile(r"\b(?:AND|OR|NOT)\b")
_PERSONAL_MARK = re.compile(r"\[(?:이름|전화|이메일|번호)\]")
_SPACES = re.compile(r"\s+")
_TITLE_NOISE = re.compile(r"[^0-9a-z가-힣]+")
MIN_TITLE_KEY_CHARS = 8


# ── 키워드 ─────────────────────────────────────────────────
def keyword_input(req: ProposalRequest) -> str:
    """키워드 LLM 에 보내는 입력 — 가제·현황·원인·한계·목표·정책 근거. 개인정보 제거, 상한."""
    parts = [
        ("가제", req.title_hint),
        ("현재 상황", req.current_state),
        ("원인", req.root_cause),
        ("한계", req.limitation),
        ("목표", req.goal),
        ("정책 근거", req.policy_basis),
    ]
    text = "\n".join(
        f"{label}: {value.strip()}" for label, value in parts if value and value.strip()
    )
    return strip_personal(text).text[:MAX_INPUT_CHARS]


def clean_keyword(value: Any, lang: str) -> str | None:
    """키워드 하나를 검증. lang=ko 는 한글이 하나 이상, en 은 한글 없이 라틴 글자가 하나 이상."""
    if not isinstance(value, str):
        return None
    text = unicodedata.normalize("NFKC", _CONTROL.sub(" ", value))
    if strip_personal(text).removed or _PERSONAL_MARK.search(text):
        return None  # 개인정보가 섞인 키워드는 통째로 버린다
    text = _OPERATORS.sub(" ", _DISALLOWED.sub(" ", text))
    text = _SPACES.sub(" ", text).strip(" -·./&+")
    if not text or len(text) > MAX_KEYWORD_CHARS:
        return None
    if lang == "ko":
        return text if _HANGUL.search(text) else None
    return text if _LATIN.search(text) and not _HANGUL.search(text) else None


def clean_list(values: Any, lang: str, *, limit: int = MAX_KEYWORDS) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for v in values[: limit * 3]:
        kw = clean_keyword(v, lang)
        if kw is None or kw.casefold() in seen:
            continue
        seen.add(kw.casefold())
        out.append(kw)
        if len(out) >= limit:
            break
    return out


def keywords_from_llm(data: Mapping[str, Any] | None, origin: KeywordOrigin) -> LiveKeywords | None:
    """LLM JSON 객체 {"ko": [...], "en": [...]} → 키워드. 국문이 하나도 없으면 None(다음 단계로)."""
    if not isinstance(data, Mapping):
        return None
    ko = clean_list(data.get("ko"), "ko")
    en = clean_list(data.get("en"), "en")
    if not ko:
        return None
    return LiveKeywords(ko=ko, en=en, origin=origin)


def rule_keywords(req: ProposalRequest, rule: KeywordRule | None = None) -> LiveKeywords:
    """규칙 기반 — 가제·목표·현황의 고유 키워드(일반어 제외, keywords.query_keywords) 앞에서부터.
    영문은 입력에 있는 라틴 글자 토큰(예: AI·IoT·LiDAR)만 — 번역은 하지 않는다."""
    rule = rule or KeywordRule()
    text = " ".join(
        p
        for p in (req.title_hint, req.goal, req.current_state, req.limitation, req.root_cause)
        if p
    )
    text = strip_personal(text).text
    tokens = query_keywords(text, rule)
    ko = clean_list([t for t in tokens if _HANGUL.search(t)], "ko")
    en = clean_list([t for t in tokens if not _HANGUL.search(t) and len(t) >= 2], "en")
    return LiveKeywords(ko=ko, en=en, origin="rule")


def top_up(primary: LiveKeywords, fallback: LiveKeywords) -> LiveKeywords:
    """LLM 키워드가 MIN_KEYWORDS 보다 적으면 규칙 기반으로 채운다 (출처 표시는 그대로)."""

    def fill(main: list[str], extra: list[str]) -> list[str]:
        out = list(main)
        seen = {k.casefold() for k in out}
        for k in extra:
            if len(out) >= MIN_KEYWORDS:
                break
            if k.casefold() not in seen:
                seen.add(k.casefold())
                out.append(k)
        return out[:MAX_KEYWORDS]

    return primary.model_copy(
        update={"ko": fill(primary.ko, fallback.ko), "en": fill(primary.en, fallback.en)}
    )


# ── 질의·캐시 키·세션 키 ───────────────────────────────────
def source_queries(keywords: Sequence[str], *, limit: int = MAX_QUERIES) -> list[str]:
    """[앞 둘 AND, 첫째, 둘째] — 앞 질의로 건수가 차면 어댑터가 뒤 질의를 보내지 않는다."""
    kws = [k for k in keywords if k]
    if not kws:
        return []
    out = [f"{kws[0]} {kws[1]}"] if len(kws) >= 2 else []
    out.extend(kws[:2])
    unique: list[str] = []
    for q in out:
        if q not in unique:
            unique.append(q)
    return unique[:limit]


def normalize_query(text: str) -> str:
    return _SPACES.sub(" ", unicodedata.normalize("NFKC", text).casefold()).strip()


def cache_key(source: str, queries: Iterable[str], limit: int) -> str:
    """자료원 + 정규화한 질의 + 건수의 sha256. 키·토큰은 들어가지 않는다 (보안 C)."""
    body = "\n".join([CACHE_VERSION, source, str(int(limit)), *map(normalize_query, queries)])
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def session_key(owner: str, req: ProposalRequest) -> str:
    """소유자 + 입력 검색 글(+정책 근거)의 sha256. 같은 입력이면 같은 세션."""
    body = "\n".join([owner, normalize_query(req.search_text()), normalize_query(req.policy_basis)])
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def session_hash(key: str) -> str:
    return key[:SESSION_HASH_CHARS]


# ── 저장 전 정리·중복 ─────────────────────────────────────
def _scrub(text: str | None) -> str | None:
    if not text:
        return text
    return strip_personal(text).text


def prepare_live(doc: Document, session: str) -> Document:
    """실시간 결과 → 저장용. 사람 이름(authors) 제거, 본문 개인정보 표식, public, live 표시."""
    raw = {**doc.raw, "live": True, "live_first_seen": session}
    return doc.model_copy(
        update={
            "authors": [],
            "abstract": _scrub(doc.abstract),
            "body": _scrub(doc.body),
            "visibility": "public",
            "raw": raw,
        }
    )


def normalized_title(title: str) -> str:
    """dedup 과 같은 제목 정규화 — 소문자, 영숫자·한글만."""
    return _TITLE_NOISE.sub("", (title or "").lower())


def identity(doc: Document) -> str:
    """교차 자료원 동일성 키 — dedup.identity_key(과제번호·보고서번호+제목·DOI·출원번호·정규화
    제목)에
    제목 키면 발행연도를 붙인다 (같은 제목의 다른 해 문서를 합치지 않는다)."""
    key = identity_key(doc)
    if key.startswith("title:"):
        return f"{key}:{doc.pub_date.year if doc.pub_date else ''}"
    return key


def title_year_key(doc: Document) -> str | None:
    """과제가 아닌 문서의 제목+연도 키 (DOI 가 한쪽에만 있는 같은 논문을 잇는다). 제목이 짧으면
    None."""
    norm = normalized_title(doc.title)
    if doc.doc_type == "rnd_project" or len(norm) < MIN_TITLE_KEY_CHARS:
        return None
    return f"title:{norm}:{doc.pub_date.year if doc.pub_date else ''}"


def identity_keys(doc: Document) -> list[str]:
    """중복 판정 키 목록 — 하나라도 같으면 같은 문서."""
    keys = [identity(doc)]
    extra = title_year_key(doc)
    if extra and extra not in keys:
        keys.append(extra)
    return keys


def dedup_live(docs: Sequence[Document]) -> tuple[list[Document], dict[str, str]]:
    """실시간 결과끼리 중복 제거 (먼저 온 것 유지 — 자료원 순서 ntis·scienceon·openalex).
    반환: (남은 문서, 빠진 doc_id → 남은 doc_id)."""
    owner: dict[str, Document] = {}  # 키 → 남은 문서
    kept: list[Document] = []
    alias: dict[str, str] = {}
    for d in docs:
        keys = identity_keys(d)
        hit = next((owner[k] for k in keys if k in owner), None)
        if hit is not None:
            if hit.doc_id != d.doc_id:
                alias[d.doc_id] = hit.doc_id
            for k in keys:
                owner.setdefault(k, hit)
            continue
        kept.append(d)
        for k in keys:
            owner[k] = d
    return kept, alias


def match_existing(new: Sequence[Document], stored: Sequence[Document]) -> dict[str, str]:
    """{새 doc_id: 저장된 doc_id} — 동일성 키가 하나라도 같은 저장 문서 (doc_id 가 다를 때만)."""
    index: dict[str, str] = {}
    for d in stored:
        for k in identity_keys(d):
            index.setdefault(k, d.doc_id)
    out: dict[str, str] = {}
    for d in new:
        found = next((index[k] for k in identity_keys(d) if k in index), None)
        if found and found != d.doc_id:
            out[d.doc_id] = found
    return out


def overall_status(results: Sequence[LiveSourceResult], *, finished: bool) -> LiveStatus:
    if not finished:
        return "pending"
    active = [r for r in results if r.status != "off"]
    if not active:
        return "off"
    return "done" if all(r.status == "ok" for r in active) else "partial"
