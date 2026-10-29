"""문서 단위 검색 (2026-10-29 [UI] 레인 3) — 위쪽 통합 검색의 "자료" 묶음과 자료 검색 화면.

hybrid_search(청크) → 문서별 첫 청크 → 문서 조회(제목·자료원·연도·원문 링크) → 연도 거르기.
저장소는 호출자가 고른다 — 공용 계정이면 PublicOnlyRepository 라 internal 은 검색에도 문서 조회에도
나오지 않는다(청크 표시·문서 표시로 두 번 막는다).
"""

from __future__ import annotations

from dataclasses import dataclass

from rra.application.ports import DocumentRepository
from rra.domain.models import Chunk, Document
from rra.domain.rules.doc_search import first_per_doc, looks_like_doc_id, year_in_range

#: 연도·자료원 거르기로 빠질 몫을 감안해 넉넉히 받는다
_OVERFETCH = 6
_MAX_FETCH = 120


@dataclass(frozen=True)
class DocumentHit:
    doc: Document
    chunk: Chunk | None  # 번호로 바로 찾은 문서는 청크가 없다


def _year(doc: Document) -> int | None:
    return doc.pub_date.year if doc.pub_date else None


class SearchDocuments:
    def __init__(self, repo: DocumentRepository):
        self.repo = repo

    async def __call__(
        self,
        query: str,
        *,
        limit: int = 5,
        sources: list[str] | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[DocumentHit]:
        query = query.strip()
        if not query or limit <= 0:
            return []
        if looks_like_doc_id(query):  # 근거 패널 [원본 보기] — 그 문서 하나
            doc = await self.repo.get_document(query.split("#", 1)[0])
            if (
                doc is not None
                and (not sources or doc.source in sources)
                and year_in_range(_year(doc), year_from, year_to)
            ):
                return [DocumentHit(doc, None)]
        chunks = await self.repo.hybrid_search(
            [query], k=min(limit * _OVERFETCH, _MAX_FETCH), sources=sources or None
        )
        out: list[DocumentHit] = []
        for chunk in first_per_doc(chunks, lambda c: c.doc_id):
            doc = await self.repo.get_document(chunk.doc_id)
            if doc is None:  # 공용 계정의 internal 또는 지워진 문서
                continue
            if not year_in_range(_year(doc), year_from, year_to):
                continue
            out.append(DocumentHit(doc, chunk))
            if len(out) >= limit:
                break
        return out
