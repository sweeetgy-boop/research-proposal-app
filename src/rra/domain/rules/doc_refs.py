"""문서 표시 — 화면에 내부 문서 번호를 내보내지 않는다 (2026-10-28 레인 B, ADR 0040).

화면은 ``own:…``·``alio:sum-…``·``ntis:…``·``f:method:t1`` 같은 내부 번호 대신 "제목 · 자료원 이름(한국어)" 을
보이고, 누르면 근거 패널(요약 + 원문 링크)을 연다. 여기에는 그 규칙만 있다(순수).

- ``SOURCE_NAMES``: 자료원 키 → 한국어 이름 (화면 배지). 프런트엔드 ``web/src/lib/docRefs.ts`` 의
  ``SOURCE_NAMES`` 와 같은 값이다(테스트가 둘을 맞춘다).
- ``doc_ref``: 뷰가 doc_id 옆에 붙이는 {title, source, source_label, url}. url 은 공개 문서만.
- ``replace_internal_ids``: LLM 출력(검토 의견·알림 문구)에 섞인 내부 번호를 제목·이름으로 바꾸거나 뺀다.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

SOURCE_NAMES: dict[str, str] = {
    "own": "사내 과제",
    "alio": "알리오 공시",
    "ntis": "NTIS 국가R&D",
    "scienceon": "ScienceON",
    "openalex": "OpenAlex 논문",
    "kipris_kr": "KIPRIS 국내 특허",
    "kipris_intl": "KIPRIS 해외 특허",
    "korail_web": "공사 홈페이지",
    "molit": "국토교통부",
    "rnd_notice": "R&D 공고",
    "g2b": "나라장터",
    "bai": "감사원",
    "mofe": "기획재정부",
    "datago": "공공데이터포털",
}
UNKNOWN_SOURCE = "수집 자료"
UNTITLED = "제목 없는 자료"

_SOURCES_RE = "|".join(sorted((re.escape(k) for k in SOURCE_NAMES), key=len, reverse=True))
# 문서·청크 번호: own:2023-001#3, alio:sum-0f3a…#1, ntis:1711…, openalex:W12345#0, korail_web:99fc…
DOC_ID = re.compile(rf"\b(?:{_SOURCES_RE}):[A-Za-z0-9_\-.:/]*[A-Za-z0-9_\-](?:#\d+)?")
# 공개 요약 번호만 따로 나온 경우 (sum-0f3a…)
SUM_ID = re.compile(r"\bsum-[0-9a-f]{6,}(?:#\d+)?")
# 그림 번호 f:<섹션>:<n> / f:<섹션>:t<n>
FIGURE_ID = re.compile(r"\bf:([a-z_]+):(t?)(\d+)\b")
_FIGURE_WORD = re.compile(r"(?:그림|figure)\s*(?=f:[a-z_]+:t?\d)")
# 문장 번호 s:<섹션>:<n>
SENTENCE_ID = re.compile(r"\bs:([a-z_]+):(\d+)\b")
# 감싼 괄호째 지울 때 — [own:…], (근거: ntis:…), 「…」 는 그대로 둔다
_WRAPPED = re.compile(
    rf"[\[(（]\s*(?:(?:근거|출처|문서|자료|doc_id|evidence)\s*[:：]\s*)?"
    rf"(?:(?:{_SOURCES_RE}):[^\])）]*|sum-[0-9a-f]{{6,}}[^\])）]*)[\])）]"
)


def source_of(doc_id: str) -> str:
    return doc_id.split(":", 1)[0] if ":" in doc_id else ""


def source_name(source: str | None) -> str:
    return SOURCE_NAMES.get(source or "", UNKNOWN_SOURCE)


def doc_ref(
    doc_id: str,
    title: str | None,
    *,
    source: str | None = None,
    url: str | None = None,
    visibility: str | None = "public",
) -> dict[str, Any]:
    """doc_id 옆에 붙이는 표시 정보. 사내 전용(internal) 문서는 원문 링크를 주지 않는다."""
    src = source or source_of(doc_id)
    return {
        "doc_id": doc_id,
        "title": (title or "").strip() or UNTITLED,
        "source": src,
        "source_label": source_name(src),
        "url": url if url and visibility != "internal" else None,
    }


def _doc_of(id_: str) -> str:
    return id_.split("#", 1)[0]


def replace_internal_ids(
    text: str,
    titles: Mapping[str, str] | None = None,
    *,
    section_titles: Mapping[str, str] | None = None,
) -> str:
    """글에 섞인 내부 번호 → 「제목」(아는 문서) 또는 지움. 그림 번호 → "<섹션> 그림 n", 문장 번호 →
    "<섹션> 문장 n". titles: 근거 id(chunk_id·doc_id) → 제목."""
    if not text:
        return text
    names = dict(titles or {})
    sections = dict(section_titles or {})

    def title_for(id_: str) -> str | None:
        found = names.get(id_) or names.get(_doc_of(id_))
        if found is None and id_.startswith("sum-"):
            found = names.get(f"alio:{id_}") or names.get(f"alio:{_doc_of(id_)}")
        return found

    def wrapped(m: re.Match[str]) -> str:
        found = DOC_ID.search(m.group(0)) or SUM_ID.search(m.group(0))
        t = title_for(found.group(0)) if found else None
        return f"「{t}」" if t else ""

    def bare(m: re.Match[str]) -> str:
        t = title_for(m.group(0))
        return f"「{t}」" if t else "관련 자료"

    def figure(m: re.Match[str]) -> str:
        sec = sections.get(m.group(1), "")
        kind = "분석 기법 그림" if m.group(2) else "그림"
        return f"{sec} {kind} {m.group(3)}".strip()

    def sentence(m: re.Match[str]) -> str:
        sec = sections.get(m.group(1), "")
        return f"{sec} 문장 {int(m.group(2)) + 1}".strip()

    out = _WRAPPED.sub(wrapped, text)
    out = DOC_ID.sub(bare, out)
    out = SUM_ID.sub(lambda m: f"「{t}」" if (t := title_for(m.group(0))) else "관련 자료", out)
    out = FIGURE_ID.sub(figure, _FIGURE_WORD.sub("", out))
    out = SENTENCE_ID.sub(sentence, out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\s+([.,)])", r"\1", out)
    return out.strip()


def has_internal_id(text: str) -> bool:
    return bool(
        DOC_ID.search(text or "")
        or SUM_ID.search(text or "")
        or FIGURE_ID.search(text or "")
        or SENTENCE_ID.search(text or "")
    )
