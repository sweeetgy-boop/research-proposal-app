"""U5 선행연구 브리핑의 순수 규칙 — 항목 선정, 연도 집계, 키워드, LLM 출력 검증.

- pick_items: 스냅샷 청크 중 논문·보고서(paper·internal_report·rnd_project) 문서당 1건, 순위 유지,
  10건.
- year_counts: 연도별 건수 ("미상" 포함).
- top_keywords: 제목·청크 본문의 키워드(일반어 제외) 빈도 상위.
- validate_brief: 요약은 그 청크 본문·제목에 없는 수치가 있으면 폐기, 한자·가나 폐기, 길이 상한.
  연구 공백 후보는 evidence 가 브리핑 항목 id 안에 있어야 하고 수치는 근거 안에서만.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from rra.domain.models import Chunk, Document
from rra.domain.models.brief import (
    MAX_GAP_CHARS,
    MAX_ITEMS,
    MAX_SUMMARY_CHARS,
    BriefItem,
    GapCandidate,
)
from rra.domain.rules.foreign_script import has_foreign_script
from rra.domain.rules.keywords import KeywordRule, query_keywords
from rra.domain.rules.llm_output import clean_sentence
from rra.domain.rules.numbers import unsupported_numbers
from rra.domain.rules.trust import escape_untrusted

BRIEF_DOC_TYPES: frozenset[str] = frozenset({"paper", "internal_report", "rnd_project"})
MAX_GAPS = 5
MAX_KEYWORDS = 12
DISCARD_NUMBER = "unsupported_number"
DISCARD_FOREIGN = "foreign_script"
DISCARD_EVIDENCE = "evidence_out_of_range"
DISCARD_EMPTY = "empty"


def pick_items(
    chunks: Iterable[Chunk], docs: Mapping[str, Document | None], limit: int = MAX_ITEMS
) -> list[tuple[Chunk, Document]]:
    out: list[tuple[Chunk, Document]] = []
    seen: set[str] = set()
    for c in chunks:
        if c.chunk_id.endswith("#overlap") or c.doc_id in seen:
            continue
        doc = docs.get(c.doc_id)
        if doc is None or doc.doc_type not in BRIEF_DOC_TYPES:
            continue
        seen.add(c.doc_id)
        out.append((c, doc))
        if len(out) >= limit:
            break
    return out


def year_counts(docs: Iterable[Document]) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in docs:
        key = str(d.pub_date.year) if d.pub_date else "미상"
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (kv[0] == "미상", kv[0])))


def top_keywords(texts: Iterable[str], rule: KeywordRule, limit: int = MAX_KEYWORDS) -> list[str]:
    counts: dict[str, int] = {}
    for t in texts:
        for kw in set(query_keywords(t, rule)):
            counts[kw] = counts.get(kw, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [k for k, n in ranked if n >= 2][:limit] or [k for k, _ in ranked[:limit]]


def _text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return clean_sentence(escape_untrusted(value))[:limit]


def validate_brief(
    data: Mapping[str, Any] | None,
    picked: list[tuple[Chunk, Document]],
) -> tuple[list[BriefItem], list[GapCandidate], list[dict[str, str]]]:
    """LLM JSON {"summaries": [{chunk_id, summary}], "gaps": [{text, evidence[]}]} → 검증된 값."""
    by_chunk = {c.chunk_id: (c, d) for c, d in picked}
    allowed_ids = set(by_chunk) | {d.doc_id for _, d in picked}
    summaries: dict[str, str] = {}
    discarded: list[dict[str, str]] = []
    raw_items = data.get("summaries") if isinstance(data, Mapping) else None
    for raw in raw_items if isinstance(raw_items, list) else []:
        if not isinstance(raw, dict):
            continue
        cid = str(raw.get("chunk_id", ""))
        if cid not in by_chunk or cid in summaries:
            discarded.append({"id": cid[:80], "reason": DISCARD_EVIDENCE})
            continue
        chunk, doc = by_chunk[cid]
        text = _text(raw.get("summary"), MAX_SUMMARY_CHARS)
        if not text:
            discarded.append({"id": cid, "reason": DISCARD_EMPTY})
            continue
        if has_foreign_script(text):
            discarded.append({"id": cid, "reason": DISCARD_FOREIGN})
            continue
        if unsupported_numbers(text, [chunk.text, doc.title, doc.abstract or ""]):
            discarded.append({"id": cid, "reason": DISCARD_NUMBER})
            continue
        summaries[cid] = text
    items = [
        BriefItem(
            doc_id=d.doc_id,
            chunk_id=c.chunk_id,
            title=d.title,
            source=d.source,
            doc_type=d.doc_type,
            year=d.pub_date.year if d.pub_date else None,
            basis=c.basis or d.text_basis,
            summary=summaries.get(c.chunk_id, ""),
            summary_missing=c.chunk_id not in summaries,
        )
        for c, d in picked
    ]
    gaps: list[GapCandidate] = []
    raw_gaps = data.get("gaps") if isinstance(data, Mapping) else None
    evidence_texts = [c.text for c, _ in picked] + [d.title for _, d in picked]
    for raw in raw_gaps if isinstance(raw_gaps, list) else []:
        if not isinstance(raw, dict) or len(gaps) >= MAX_GAPS:
            continue
        text = _text(raw.get("text"), MAX_GAP_CHARS)
        ev = [str(e) for e in (raw.get("evidence") or []) if isinstance(e, str)]
        ev = list(dict.fromkeys(e for e in ev if e in allowed_ids))
        if not text:
            discarded.append({"id": "gap", "reason": DISCARD_EMPTY})
            continue
        if not ev:
            discarded.append({"id": "gap", "reason": DISCARD_EVIDENCE})
            continue
        if has_foreign_script(text):
            discarded.append({"id": "gap", "reason": DISCARD_FOREIGN})
            continue
        if unsupported_numbers(text, evidence_texts):
            discarded.append({"id": "gap", "reason": DISCARD_NUMBER})
            continue
        gaps.append(GapCandidate(text=text, evidence=ev))
    return items, gaps, discarded
