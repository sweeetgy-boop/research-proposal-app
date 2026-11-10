"""유추 최종 5건 정렬 — 문제 정의 카드 기준 (ADR 0065, 계약 problem-card.md 4절 `analogy_rank`).

순수 함수. 종전 규칙(하한·철도 분야 제외·같은 제목 제외)을 지난 후보를 받아:

1. `require_object` 면 카드의 대상어(`terms.objects_ko`·`objects_en` — 구체 단 + 일반화 단)가
   문서(제목·초록·키워드)에 나온 자료만 남긴다. 영문 자료도 같다. 작용어만 겹친 자료는 뺀다
   ("방지" 하나 겹친 제연설비 자료가 들어오던 것).
2. 유사도 상위 `rerank_top` 건을 재순위 점수(cross-encoder, 질의 = 기능 문장) 순으로 놓는다.
   점수는 **순서에만** 쓴다 — 절대값이 낮아(대부분 0.1~0.3) 하한으로 쓰지 않는다.
   점수가 없으면(reranker 없음·실패) (공유 문제어 수, 유사도) 순.
3. 순위대로 자료원당 `per_source` 건까지 먼저 담고, 모자라면 넘긴 것을 순위대로 채운다
   (상위가 한 자료원에 몰린 사례에서 약한 자료로 내려가지 않게). 결과는 순위 순.

낱말 겹침은 종전 `novelty.shared_terms` 와 같은 방식(문서 낱말이 문제어로 시작하면)이고,
여러 낱말로 된 문제어는 낱말이 모두 나와야 겹친 것으로 본다. 공유 문제어에 장소어는 없다 —
카드 문제어(대상어·작용어)만 본다.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from rra.domain.models import Document
from rra.domain.models.problem_card import CardRank, ProblemCard
from rra.domain.rules.novelty import doc_tokens

_HANGUL = re.compile(r"[가-힣]")
FEW_ANALOGIES = 3  # 유추 결과가 이보다 적으면 `few_analogies` 신호(기록만)


@dataclass(frozen=True)
class RankRow:
    """정렬 대상 한 건. objects: 문서에 나온 대상어, shared: 문서에 나온 문제어(대상어 먼저)."""

    doc: Document
    similarity: float
    objects: tuple[str, ...] = ()
    shared: tuple[str, ...] = ()
    score: float | None = field(default=None, compare=False)  # 재순위 점수(순서에만)


def _hit(term: str, toks: Sequence[str]) -> bool:
    words = term.lower().split()
    if not words:
        return False
    for w in words:
        if _HANGUL.search(w):
            if not any(d.startswith(w) for d in toks):
                return False
        elif not any(d.startswith(w) for d in toks if not _HANGUL.search(d)):
            return False
    return True


def _found(terms: Sequence[str], toks: Sequence[str]) -> list[str]:
    out: list[str] = []
    for t in terms:
        if t not in out and _hit(t, toks):
            out.append(t)
    return out


def object_hits(card: ProblemCard, doc: Document) -> list[str]:
    """문서에 나온 카드 대상어(국문 → 영문 순)."""
    toks = doc_tokens(doc)
    return _found([*card.terms.objects_ko, *card.terms.objects_en], toks)


def card_shared_terms(card: ProblemCard, doc: Document) -> list[str]:
    """문서에 나온 카드 문제어 — 대상어 먼저, 그다음 작용어. `why_relevant` 에 쓴다."""
    toks = doc_tokens(doc)
    terms = card.terms
    return _found(
        [*terms.objects_ko, *terms.objects_en, *terms.actions_ko, *terms.actions_en], toks
    )


def rank_rows(
    candidates: Sequence[tuple[Document, float]], card: ProblemCard, rank: CardRank
) -> list[RankRow]:
    """후보(종전 규칙 통과분) → 대상어 겹침을 본 정렬 대상. 유사도 높은 순, 상위 `rerank_top` 건."""
    rows: list[RankRow] = []
    for doc, similarity in candidates:
        toks = doc_tokens(doc)
        terms = card.terms
        objects = _found([*terms.objects_ko, *terms.objects_en], toks)
        if rank.require_object and not objects:
            continue
        actions = [
            t for t in _found([*terms.actions_ko, *terms.actions_en], toks) if t not in objects
        ]
        rows.append(
            RankRow(
                doc=doc,
                similarity=float(similarity),
                objects=tuple(objects),
                shared=(*objects, *actions),
            )
        )
    rows.sort(key=lambda r: (-r.similarity, r.doc.doc_id))
    return rows[: rank.rerank_top]


def order_rows(rows: Sequence[RankRow], scores: Sequence[float] | None = None) -> list[RankRow]:
    """재순위 점수 순(같으면 유사도). 점수가 없거나 개수가 맞지 않으면 (공유 문제어 수, 유사도)
    순."""
    if scores is not None and len(scores) == len(rows):
        scored = [
            RankRow(r.doc, r.similarity, r.objects, r.shared, float(s))
            for r, s in zip(rows, scores, strict=True)
        ]
        return sorted(scored, key=lambda r: (-(r.score or 0.0), -r.similarity, r.doc.doc_id))
    return sorted(rows, key=lambda r: (-len(r.shared), -r.similarity, r.doc.doc_id))


def take_by_source(
    ordered: Sequence[RankRow], *, per_source: int, limit: int, window: int | None = None
) -> list[RankRow]:
    """순위대로 자료원당 per_source 건까지 먼저, limit 이 안 차면 넘긴 것을 순위대로.
    결과는 순위 순.

    window: 자료원당 우선을 적용하는 범위(순위 상위 몇 건). 그 밖의 자료는 '넘긴 것'보다 먼저
    담지 않는다 — 상위가 한 자료원에 몰렸을 때 순위가 한참 낮은 다른 자료원 자료가 들어오지
    않게. None 이면 범위 제한 없음."""
    if limit <= 0:
        return []
    head = ordered if window is None else ordered[: max(window, limit)]
    counts: dict[str, int] = {}
    picked: list[int] = []
    skipped: list[int] = []
    for i, row in enumerate(head):
        if len(picked) >= limit:
            break
        if counts.get(row.doc.source, 0) >= per_source:
            skipped.append(i)
            continue
        counts[row.doc.source] = counts.get(row.doc.source, 0) + 1
        picked.append(i)
    for i in [*skipped, *range(len(head), len(ordered))]:
        if len(picked) >= limit:
            break
        picked.append(i)
    return [ordered[i] for i in sorted(picked)]


def few_analogies(count: int) -> bool:
    """유추 결과가 3건 미만 — 신호만 기록한다(재검색 없음, 계약 4절)."""
    return count < FEW_ANALOGIES
