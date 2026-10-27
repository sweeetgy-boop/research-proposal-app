"""U3 섹션별 AI 다시 쓰기의 순수 규칙.

- 보존 문장: origin 이 proposer_edit·proposer_input·proposer·app 인 문장은 다시 쓰지 않고 원래
  자리(인덱스)에 둔다. 선택값(choices)은 바꾸지 않는다.
- 후보 합치기: 새 문장 목록에 보존 문장을 원래 인덱스(또는 끝)에 끼워 넣는다.
- 적용: 제안자가 고른 후보 인덱스만 새 섹션으로. 고르지 않으면 전부.
"""

from __future__ import annotations

from collections.abc import Iterable

from rra.domain.models import Section, Sentence

PRESERVED_ORIGINS: frozenset[str] = frozenset(
    {"proposer_edit", "proposer_input", "proposer", "app"}
)
REWRITE_NOTE = "AI 다시 쓰기"


def preserved(section: Section) -> list[tuple[int, Sentence]]:
    return [(i, s) for i, s in enumerate(section.sentences) if s.origin in PRESERVED_ORIGINS]


def merge_candidate(current: Section, new_sentences: Iterable[Sentence]) -> Section:
    """새 문장 + 보존 문장(원래 인덱스) → 후보 섹션. 선택값은 현재 것 그대로."""
    out: list[Sentence] = list(new_sentences)
    for idx, sentence in preserved(current):
        out.insert(min(idx, len(out)), sentence)
    return Section(key=current.key, sentences=out, choices=list(current.choices))


def pick(candidate: Section, chosen: list[int] | None) -> Section:
    """고른 인덱스의 문장만 (순서는 인덱스 순). 보존 문장은 고르지 않아도 남긴다."""
    if chosen is None:
        return candidate
    keep = set(chosen)
    sentences = [
        s for i, s in enumerate(candidate.sentences) if i in keep or s.origin in PRESERVED_ORIGINS
    ]
    return candidate.model_copy(update={"sentences": sentences})


def side_by_side(current: Section, candidate: Section) -> list[dict]:
    """화면용 — 같은 인덱스의 현재 문장과 후보 문장을 나란히."""
    n = max(len(current.sentences), len(candidate.sentences))
    rows = []
    for i in range(n):
        cur = current.sentences[i] if i < len(current.sentences) else None
        cand = candidate.sentences[i] if i < len(candidate.sentences) else None
        rows.append(
            {
                "index": i,
                "current": None
                if cur is None
                else {"text": cur.text, "evidence": list(cur.evidence), "origin": cur.origin},
                "candidate": None
                if cand is None
                else {
                    "text": cand.text,
                    "evidence": list(cand.evidence),
                    "origin": cand.origin,
                    "preserved": cand.origin in PRESERVED_ORIGINS,
                },
            }
        )
    return rows
