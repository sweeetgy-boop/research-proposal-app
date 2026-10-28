"""② 같은 연작 묶기 — 제목이 연도·차수만 다른 과제를 한 줄로 (순수, 2026-10-29 레인 A, ADR 0043).

시범 측정(골든셋 08)에서 ② 표 상위 10칸이 모두 「20xx년도 ○○철도 수송수요 예측 연구」 연작이라
다른 과제가 표에 들지 못했다. 소유자 정의: "제목이 연도·차수만 다른 것" 이 같은 연작이다.

- ``display_title``: 화면 제목 정리 — 공시용 요약문 머리("요 약 문 1. 연구 제목 …",
  "연구과제 요약서 1. 연구제목 …")와 꼬리("□ 개 요")를 뗀다. 적재(own_docs)도 이 규칙으로 제목을
  정리하되 문서 번호는 뗀 전 제목에서 나온 그대로 둔다.
- ``series_key``: 연작 키 — 연도(2026년도·2017년·'23년·2026)·연도 범위((2020~2029)·2025~2045)·
  괄호 연도((2023))·차수(제2차·2차·3차년도·(1단계))를 빼고, 공백·문장부호와 단독 "및", 끝의
  "연구"·"용역"을 없앤 글자. 키가 같으면 한 연작이다.
  판단(ADR 0043): "중장기"·"단기"·"광역철도"·"고속철도"·"일반철도"·"KTX" 같은 낱말은 남긴다 — 예측
  기간과 노선 종류가 다르면 다른 과제다(연도·차수만 다른 것이 아니다).
- ``series_label``: 화면 라벨 — 연도·차수를 뺀 제목(공백 유지, "광역철도 수송수요 예측").
- ``merge_series``: 판정 행을 연작 하나에 한 행으로. 대표 = 점수(reranker, 없으면 e5) 가장 높은 행,
  나머지 doc_id(후보 풀에서 같은 키인 문서 포함)는 ``merged_ids`` 에 — 선택·차단("하나라도 차단이면
  차단")·비교표·측정이 그대로 돈다. 판(제목)이 둘 이상이면 ``series`` 정보를 붙인다(하나뿐이면 같은
  제목 묶음 — 종전 merge_same_titles 와 같다).
"""

from __future__ import annotations

import re
import unicodedata
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from rra.domain.models import Document, OverlapAlert
from rra.domain.models.gap import SeriesDoc, SeriesEdition, SeriesInfo
from rra.domain.rules.similar_choice import title_key

MIN_SERIES_KEY = 5  # 이보다 짧은 연작 키("연구"만 남은 제목 등)는 묶지 않는다
MAX_SUMMARY_CHARS = 300

# ── 화면 제목 정리 ────────────────────────────────────────
_SP = r"\s*"
_JUNK_HEAD = re.compile(
    r"^\s*(?:"
    r"요\s*약\s*문|연\s*구\s*과\s*제\s*요\s*약\s*(?:서|보\s*고\s*서)|연\s*구\s*요\s*약\s*(?:서|보\s*고\s*서)"
    r")\s*(?:\d{1,2}\s*[.)]\s*)?"
    r"(?:연\s*구\s*(?:과\s*제\s*)?(?:제\s*목|명)|과\s*제\s*명)?\s*[:：]?\s*[◦○•·▶\-]*\s*"
)
_JUNK_TAIL = re.compile(r"\s*[□■○◦]\s*(?:개\s*요|목\s*차|요\s*약)\s*$")
_SPACES = re.compile(r"\s+")


def display_title(title: str) -> str:
    """공시용 요약문 머리·꼬리를 뗀 화면 제목. 남는 게 없으면 원래 제목."""
    text = unicodedata.normalize("NFC", title or "").strip()
    cleaned = _JUNK_TAIL.sub("", _JUNK_HEAD.sub("", text, count=1))
    cleaned = _SPACES.sub(" ", cleaned).strip()
    return cleaned or _SPACES.sub(" ", text).strip()


# ── 연작 키 ──────────────────────────────────────────────
_TILDES = str.maketrans({"∼": "~", "～": "~", "〜": "~", "∽": "~"})
_Y = r"(?:19|20)\d{2}"
# 연도 범위: (2020~2029) · 2025~2045 · 2020-2029년 · (2026~55)
_RANGE = re.compile(rf"\(?\s*{_Y}\s*년?\s*[~\-–—]\s*(?:{_Y}|\d{{2}})\s*년?\s*\)?")
# 괄호 연도: (2023) · (2023년) · (2023년도)
_PAREN_YEAR = re.compile(rf"\(\s*{_Y}\s*(?:년\s*도?)?\s*\)")
# 연도: 2026년도 · 2017년 · '23년 · ’23년도
_YEAR_WORD = re.compile(rf"(?:{_Y}|[’'‘]\d{{2}})\s*년\s*도?")
_BARE_YEAR = re.compile(rf"(?<![\d.])({_Y})(?![\d.])")
# 차수·단계: 제2차 · 3차년도 · (2차) · 끝의 2차 · (1단계) · 제1단계 · 끝의 2단계
_EDITION = re.compile(
    r"제\s*\d{1,2}\s*(?:차\s*(?:년\s*도)?|단\s*계)"
    r"|\(\s*\d{1,2}\s*(?:차\s*(?:년\s*도)?|단\s*계)\s*\)"
    r"|(?<!\d)\d{1,2}\s*차\s*년\s*도"
    r"|(?<!\d)\d{1,2}\s*(?:차|단\s*계)\s*$"
)
_AND = re.compile(r"(?<![가-힣])및(?![가-힣])")
_TAIL_WORDS = re.compile(r"(?:\s*(?:연\s*구\s*용\s*역|연\s*구|용\s*역))+\s*$")
# 라벨은 "…에 관한 연구" 처럼 문장이 끝나는 "연구" 는 남긴다
_SENTENCE_END = re.compile(r"(?:관한|대한|위한)\s*연\s*구\s*$")
_EMPTY_PAREN = re.compile(r"\(\s*\)")
_KEY_NOISE = re.compile(r"[^0-9a-z가-힣]+")


def _strip_editions(title: str) -> str:
    text = display_title(title).translate(_TILDES)
    for rx in (_RANGE, _PAREN_YEAR, _YEAR_WORD, _EDITION):
        text = rx.sub(" ", text)
    text = _BARE_YEAR.sub(" ", text)
    text = _EMPTY_PAREN.sub(" ", text)
    return _SPACES.sub(" ", text).strip(" ,·-~")


def series_key(title: str) -> str:
    """연작 키 — 연도·차수·공백·문장부호·단독 "및"·끝의 "연구/용역" 을 뺀 글자(소문자)."""
    text = _AND.sub(" ", _strip_editions(title))
    text = _TAIL_WORDS.sub("", text)
    return _KEY_NOISE.sub("", text.lower())


def series_label(title: str) -> str:
    """화면 라벨 — 연도·차수를 뺀 제목(공백 유지). "2026년도 광역철도 수송수요 예측 연구" →
    "광역철도 수송수요 예측"."""
    text = _strip_editions(title)
    if not _SENTENCE_END.search(text):
        text = _TAIL_WORDS.sub("", text)
    text = text.strip(" ,·-~")
    return text or display_title(title)


def group_key(title: str) -> str:
    """행 묶음 키 — 연작 키가 충분히 길면 그것, 아니면 같은 제목 키(종전 merge_same_titles)."""
    key = series_key(title)
    if len(key) >= MIN_SERIES_KEY:
        return "s:" + key
    same = title_key(title)
    return "t:" + same if len(same) >= 4 else ""


def title_year(title: str, fallback: int | None = None) -> int | None:
    """판의 연도 — "N년(도)" > 괄호 연도 "(2023)" > 연도 범위의 시작 > 맨 연도 > fallback
    (발간 연도)."""
    text = display_title(title).translate(_TILDES)
    for rx in (_YEAR_WORD, _PAREN_YEAR, _RANGE, _BARE_YEAR):
        m = rx.search(text)
        if m:
            found = re.search(_Y, m.group(0))
            if found:
                return int(found.group(0))
    return fallback


def series_display(label: str, count: int) -> str:
    """소유자 문구: "광역철도 수송수요 예측(연작 7건)"."""
    return f"{label}(연작 {count}건)"


# ── 설정 ────────────────────────────────────────────────
class SeriesRule(BaseModel):
    """config/overlap.yaml `series` (ADR 0043)."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    # 후보 검색을 이만큼 넓게 받아 연작으로 묶은 뒤에도 표가 서로 다른 과제 k 줄을 채운다
    fetch_multiplier: int = Field(default=4, ge=1, le=10)
    # reranker 에는 연작마다 e5 상위 몇 건만 보낸다 (나머지는 묶음 구성원으로만)
    rerank_per_series: int = Field(default=2, ge=1, le=10)
    # reranker 에 보내는 최대 건수 (0 = k × rerank_multiplier)
    rerank_max: int = Field(default=0, ge=0, le=200)


# ── 후보 묶기 ────────────────────────────────────────────
def group_hits(
    hits: Iterable[tuple[Document, float]], key: Callable[[str], str] = group_key
) -> OrderedDict[str, list[tuple[Document, float]]]:
    """(문서, 유사도) → 묶음 키별 목록 (처음 나온 순서, 안은 입력 순서). 키가 빈 문서는 혼자."""
    groups: OrderedDict[str, list[tuple[Document, float]]] = OrderedDict()
    for doc, sim in hits:
        k = key(doc.title) or f"d:{doc.doc_id}"
        groups.setdefault(k, []).append((doc, sim))
    return groups


def pick_for_rerank(
    groups: Mapping[str, Sequence[tuple[Document, float]]], per_series: int, limit: int
) -> list[tuple[Document, float]]:
    """reranker 입력 — 묶음 순서대로 묶음마다 상위 per_series 건, 모두 limit 건까지."""
    out: list[tuple[Document, float]] = []
    for members in groups.values():
        for item in members[:per_series]:
            if len(out) >= limit:
                return out
            out.append(item)
    return out


def _score(a: OverlapAlert) -> tuple[float, float]:
    return (a.rerank_score if a.rerank_score is not None else -1.0, a.similarity)


def _edition_of(doc_id: str, title: str, docs: Mapping[str, Document]) -> tuple[str, int | None]:
    doc = docs.get(doc_id)
    year = doc.pub_date.year if doc is not None and doc.pub_date else None
    return display_title(title), title_year(title, year)


def _series_info(
    key: str,
    best: OverlapAlert,
    member_ids: Sequence[str],
    titles: Mapping[str, str],
    docs: Mapping[str, Document],
) -> SeriesInfo | None:
    editions: OrderedDict[str, SeriesEdition] = OrderedDict()
    for doc_id in member_ids:
        title = titles.get(doc_id, "")
        shown, year = _edition_of(doc_id, title, docs)
        ek = title_key(shown) or doc_id
        doc = docs.get(doc_id)
        entry = SeriesDoc(
            doc_id=doc_id,
            source=doc.source if doc is not None else doc_id.split(":", 1)[0],
            url=doc.url if doc is not None else None,
            visibility=doc.visibility if doc is not None else "public",
        )
        if ek in editions:
            editions[ek].docs.append(entry)
            continue
        summary = ""
        if doc is not None:
            summary = " ".join(p for p in (doc.abstract, doc.body) if p)[:MAX_SUMMARY_CHARS]
        editions[ek] = SeriesEdition(title=shown, year=year, docs=[entry], summary=summary)
    if len(editions) < 2:
        return None
    members = sorted(editions.values(), key=lambda e: (e.year is None, e.year or 0, e.title))
    return SeriesInfo(
        key=key,
        label=series_label(best.title),
        count=len(members),
        members=members,
    )


def merge_series(
    alerts: Sequence[OverlapAlert],
    docs: Mapping[str, Document] | None = None,
    pool: Iterable[tuple[Document, float]] = (),
    key: Callable[[str], str] = group_key,
) -> list[OverlapAlert]:
    """연작(또는 같은 제목) 하나에 한 행. 행 순서 = 묶음이 처음 나온 순서, 차단 행 먼저(안정 정렬).

    대표 = 점수가 가장 높은 행. 차단·규칙 차단은 하나라도면 참, 키워드는 합친다. pool(후보 풀의 다른
    문서 — reranker 에 보내지 않은 구성원)은 같은 키의 행이 있을 때만 그 행의 merged_ids·연작 목록에
    들어간다."""
    by_doc: dict[str, Document] = dict(docs or {})
    pool_by_key: OrderedDict[str, list[Document]] = OrderedDict()
    for doc, _ in pool:
        by_doc.setdefault(doc.doc_id, doc)
        k = key(doc.title)
        if k:
            pool_by_key.setdefault(k, []).append(doc)

    order: list[str] = []
    rows: dict[str, list[OverlapAlert]] = {}
    for a in alerts:
        k = key(a.title) or f"d:{a.doc_id}"
        if k not in rows:
            rows[k] = []
            order.append(k)
        rows[k].append(a)

    out: list[OverlapAlert] = []
    for k in order:
        group = rows[k]
        best = max(group, key=_score)
        titles: dict[str, str] = {}
        ids: list[str] = []
        for a in [best, *[g for g in group if g is not best]]:
            for i in [a.doc_id, *a.merged_ids]:
                if i not in titles:
                    titles[i] = a.title if i == a.doc_id else _title_of(i, by_doc, a.title)
                    ids.append(i)
        for doc in pool_by_key.get(k, []):
            if doc.doc_id not in titles:
                titles[doc.doc_id] = doc.title
                ids.append(doc.doc_id)
        update: dict[str, Any] = {
            "merged_ids": [i for i in ids if i != best.doc_id],
            "keywords": list(dict.fromkeys(kw for a in [best, *group] for kw in a.keywords)),
            "blocking": any(a.blocking for a in group),
            "rule_blocking": any(bool(a.rule_blocking) for a in group),
            "similarity": max(a.similarity for a in group),
        }
        if k.startswith("s:"):
            update["series"] = _series_info(k[2:], best, ids, titles, by_doc)
        out.append(best.model_copy(update=update))
    return sorted(out, key=lambda a: -int(a.blocking))


def _title_of(doc_id: str, docs: Mapping[str, Document], fallback: str) -> str:
    doc = docs.get(doc_id)
    return doc.title if doc is not None else fallback


def member_titles(alert: OverlapAlert, limit: int = 8, *, public_only: bool = False) -> list[str]:
    """AI 같음 판정 프롬프트용 — 연작 판 제목(연도 순, 최대 limit). public_only 면 공개 문서가 있는
    판만(외부 전송 범위 — internal 제외)."""
    if alert.series is None:
        return []
    members = [
        m
        for m in alert.series.members
        if not public_only or any(d.visibility != "internal" for d in m.docs)
    ]
    return [m.title for m in members[:limit]]
