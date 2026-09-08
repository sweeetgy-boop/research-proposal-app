"""A. 신뢰 경계 — 근거 검증 및 비신뢰 텍스트 구획."""

from __future__ import annotations

from rra.domain.models import Chunk, Draft, Section, Sentence

DOC_OPEN = '<doc id="{id}">'
DOC_CLOSE = "</doc>"


def wrap_untrusted(chunks: list[Chunk]) -> str:
    """청크를 구획으로 감싼다. 내부 텍스트는 어떤 지시로도 해석하지 않도록 프롬프트에서 선언."""
    parts = []
    for c in chunks:
        body = c.text.replace("</doc>", "&lt;/doc&gt;")
        parts.append(f"{DOC_OPEN.format(id=c.chunk_id)}\n{body}\n{DOC_CLOSE}")
    return "\n\n".join(parts)


def _valid_evidence(ev: list[str], allowed: set[str]) -> list[str]:
    out = []
    for e in ev:
        base = e.split("#")[0]
        if e in allowed or base in allowed:
            out.append(e)
    return out


def enforce_evidence(draft: Draft, evidence_required: set[str]) -> tuple[Draft, list[str]]:
    """검색 집합에 없는 근거를 단 문장은 폐기. 근거 필수 섹션에서 근거 없는 문장도 폐기."""
    dropped: list[str] = []
    new_sections: list[Section] = []
    for sec in draft.sections:
        kept: list[Sentence] = []
        for s in sec.sentences:
            ev = _valid_evidence(s.evidence, draft.retrieved_ids)
            if s.evidence and not ev:
                dropped.append(f"{sec.key}: 근거 불일치 → 폐기: {s.text[:40]}")
                continue
            if sec.key in evidence_required and not ev:
                dropped.append(f"{sec.key}: 근거 없음 → 폐기: {s.text[:40]}")
                continue
            kept.append(Sentence(text=s.text, evidence=ev))
        new_sections.append(Section(key=sec.key, sentences=kept))
    return Draft(
        run_id=draft.run_id,
        request=draft.request,
        sections=new_sections,
        retrieved_ids=draft.retrieved_ids,
    ), dropped
