"""공고문 대조 (`rra notices match`, POST /v1/ideas/notices) — #13 선행 훅, P2-7.

입력(5슬롯)으로 저장소를 rnd_notice 자료원만 검색(hybrid_search sources 필터)하고, 접수 마감이
지나지 않은 공고(valid_until ≥ 오늘; 저장소가 만료 문서를 이미 거르지만 여기서 한 번 더 확인) 상위
3건을 돌려준다. LLM 없음. 결과는 제안서에 자동으로 들어가지 않는다 — 제안자가 공고를 고르면 #13 의
notice_id 로 이어진다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from rra.application.ports import DocumentRepository
from rra.domain.models import MAX_NOTICE_MATCHES, Chunk, Document, NoticeMatch, ProposalRequest
from rra.domain.rules.notices import days_left, is_open, parse_date
from rra.domain.rules.retrieval_scope import NOTICE_DOC_TYPES

NOTICE_SOURCES = ["rnd_notice"]


class NoticeMatcher:
    def __init__(
        self,
        repo: DocumentRepository,
        *,
        k: int = MAX_NOTICE_MATCHES,
        search_multiplier: int = 6,
        today: Callable[[], date] = date.today,
    ):
        self.repo = repo
        self.k = k
        self.search_multiplier = search_multiplier
        self.today = today

    async def __call__(self, req: ProposalRequest) -> list[NoticeMatch]:
        query = req.search_text()
        chunks = await self.repo.hybrid_search(
            [query], k=self.k * self.search_multiplier, sources=NOTICE_SOURCES
        )
        today = self.today()
        best: dict[str, tuple[Document, Chunk]] = {}
        for chunk in chunks:
            if chunk.doc_id in best:
                continue
            doc = await self.repo.get_document(chunk.doc_id)
            if doc is None or doc.doc_type not in NOTICE_DOC_TYPES:
                continue
            deadline = _deadline(doc)
            if not is_open(deadline, today) or not doc.is_valid_on(today):
                continue
            best[chunk.doc_id] = (doc, chunk)
        items = [self._match(doc, chunk, today) for doc, chunk in best.values()]
        items.sort(key=lambda m: (-(m.similarity or 0.0), m.deadline or date.max, m.doc_id))
        return items[: self.k]

    @staticmethod
    def _match(doc: Document, chunk: Chunk, today: date) -> NoticeMatch:
        notice = doc.raw.get("notice") if isinstance(doc.raw.get("notice"), dict) else {}
        deadline = _deadline(doc)
        return NoticeMatch(
            doc_id=doc.doc_id,
            title=doc.title,
            agency=str(notice.get("agency") or "")[:120] or None,
            program=str(notice.get("program") or "")[:200] or None,
            posted=doc.pub_date,
            deadline=deadline,
            days_left=days_left(deadline, today),
            url=doc.url,
            similarity=chunk.similarity,
        )


def _deadline(doc: Document) -> date | None:
    if doc.valid_until is not None:
        return doc.valid_until
    notice = doc.raw.get("notice") if isinstance(doc.raw.get("notice"), dict) else {}
    return parse_date(str(notice.get("deadline") or ""))
