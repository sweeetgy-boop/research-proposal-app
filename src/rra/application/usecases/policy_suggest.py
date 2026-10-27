"""정책 근거 추천 (`rra policy-suggest`, POST /v1/ideas/policy-suggestions).

① 입력(5슬롯 + 있으면 policy_basis)으로 저장소를 korail_web 자료원만 검색(hybrid_search sources
필터)하고, doc_type 이 policy 인 문서의 청크에서 문구를 고른다. LLM 을 쓰지 않는다. 결과는 제안서에
자동으로 들어가지 않는다
— 제안자가 고른 것만 apply_policy_suggestion 으로 policy_basis 에 붙는다.
"""

from __future__ import annotations

from datetime import date

from rra.application.ports import DocumentRepository
from rra.domain.models import MAX_SUGGESTIONS, Chunk, Document, PolicySuggestion, ProposalRequest
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.policy_phrases import pick_quote, rank
from rra.domain.rules.retrieval_scope import POLICY_DOC_TYPES

POLICY_SOURCES = ["korail_web"]


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
            if doc is None or doc.doc_type not in POLICY_DOC_TYPES:
                continue
            found.append(self._suggestion(doc, chunk, query))
        return rank(found)[: self.k]

    def _suggestion(self, doc: Document, chunk: Chunk, query: str) -> PolicySuggestion:
        quote, hits = pick_quote(chunk.text, query, self.keywords)
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
