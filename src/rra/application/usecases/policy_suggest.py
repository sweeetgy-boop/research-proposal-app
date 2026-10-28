"""정책 근거 추천 (`rra policy-suggest`, POST /v1/ideas/policy-suggestions).

① 입력(5슬롯 + 있으면 policy_basis)으로 저장소를 정책 자료원만 검색(hybrid_search sources 필터)하고,
정책 문서의 청크에서 문구를 고른다. 자료원·자료 종류·관련도는 정책적 중요도 작성안(policy_cards)과
같은 규칙(domain/rules/policy_cards.policy_passage, doc_category.is_policy_basis — 2026-10-28 레인
B,
ADR 0040): 국토부 계획·공사 경영목표·전략·감사 지적·정부 R&D 공고만, 사전정보공표 연구용역(사내
발주)·
행정 공시·사업 현황은 빠진다. LLM 을 쓰지 않는다. 결과는 제안서에 자동으로 들어가지 않는다
— 제안자가 고른 것만 apply_policy_suggestion 으로 policy_basis 에 붙는다.
"""

from __future__ import annotations

from datetime import date

from rra.application.ports import DocumentRepository
from rra.domain.models import MAX_SUGGESTIONS, Chunk, Document, PolicySuggestion, ProposalRequest
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.policy_cards import CARD_SOURCES, policy_passage
from rra.domain.rules.policy_phrases import rank

POLICY_SOURCES = list(CARD_SOURCES)  # 작성안과 같은 자료원 (rnd_notice: 공고문도 후보, P2-7)


class PolicySuggest:
    def __init__(
        self,
        repo: DocumentRepository,
        *,
        k: int = MAX_SUGGESTIONS,
        search_multiplier: int = 6,
        keywords: KeywordRule | None = None,
    ):
        self.repo = repo
        self.k = k
        self.search_multiplier = search_multiplier
        self.keywords = keywords or KeywordRule()

    async def __call__(self, req: ProposalRequest) -> list[PolicySuggestion]:
        query = " ".join(p for p in (req.search_text(), req.policy_basis) if p)
        chunks = await self.repo.hybrid_search(
            [query], k=self.k * self.search_multiplier, sources=POLICY_SOURCES
        )
        docs: dict[str, Document | None] = {}
        found: list[PolicySuggestion] = []
        for chunk in chunks:
            if chunk.doc_id not in docs:
                docs[chunk.doc_id] = await self.repo.get_document(chunk.doc_id)
            doc = docs[chunk.doc_id]
            passage = policy_passage(doc, chunk.text, chunk.similarity, query, self.keywords)
            if passage is None or doc is None:
                continue
            found.append(self._suggestion(doc, chunk, *passage))
        return rank(found)[: self.k]

    def _suggestion(
        self, doc: Document, chunk: Chunk, quote: str, hits: list[str]
    ) -> PolicySuggestion:
        page = chunk.heading or (
            f"{doc.raw['pages']}쪽 문서" if isinstance(doc.raw.get("pages"), int) else None
        )
        return PolicySuggestion(
            doc_id=doc.doc_id,
            title=doc.title,
            year=_year(doc),
            page=page[:120] if page else None,
            quote=quote,
            url=doc.url,
            menu_path=str(doc.raw.get("menu_path") or "")[:200] or None,
            keywords=hits,
            similarity=chunk.similarity,
        )


def _year(doc: Document) -> int | None:
    if isinstance(doc.pub_date, date):
        return doc.pub_date.year
    snap = doc.raw.get("crawl_snapshot")
    return int(str(snap)[:4]) if isinstance(snap, str) and str(snap)[:4].isdigit() else None
