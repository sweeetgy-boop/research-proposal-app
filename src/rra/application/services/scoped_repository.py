"""자료 범위 제한 저장소 — 공용 계정(guest)은 `visibility=internal` 문서를 보지 못한다 (레인 A).

DocumentRepository 포트를 감싸 검색·유사과제·문서 조회 결과에서 internal 을 뺀다. 그 밖의 메서드
(count_by_source·facts_for 등)는 안쪽 저장소로 그대로 넘긴다. 순수 필터 — 어댑터가 아니라
application 에 둔다 (어댑터마다 같은 규칙을 다시 쓰지 않도록).
"""

from __future__ import annotations

from typing import Any

from rra.domain.models import Chunk, Document

INTERNAL = "internal"
_OVERFETCH = 3


def is_public(doc: Document | None) -> bool:
    return doc is not None and (doc.visibility or "public") != INTERNAL


class PublicOnlyRepository:
    def __init__(self, inner: Any):
        self._inner = inner

    def __getattr__(self, name: str) -> Any:  # 나머지는 위임 (upsert·count_by_source·facts …)
        return getattr(self._inner, name)

    def __repr__(self) -> str:
        return f"PublicOnlyRepository({self._inner!r})"

    async def hybrid_search(
        self,
        queries: list[str],
        *,
        k: int = 20,
        orgs: list[str] | None = None,
        sources: list[str] | None = None,
    ) -> list[Chunk]:
        found = await self._inner.hybrid_search(
            queries, k=min(k * _OVERFETCH, 200), orgs=orgs, sources=sources
        )
        out: list[Chunk] = []
        for chunk in found:
            vis = getattr(chunk, "visibility", None)
            if vis is None:  # 청크에 표시가 없으면 문서로 확인
                doc = await self._inner.get_document(chunk.doc_id)
                if not is_public(doc):
                    continue
            elif vis == INTERNAL:
                continue
            out.append(chunk)
            if len(out) >= k:
                break
        return out

    async def find_similar(self, text: str, *, k: int = 10) -> list[tuple[Document, float]]:
        hits = await self._inner.find_similar(text, k=min(k * _OVERFETCH, 200))
        return [(d, s) for d, s in hits if is_public(d)][:k]

    async def get_document(self, doc_id: str) -> Document | None:
        doc = await self._inner.get_document(doc_id)
        return doc if is_public(doc) else None
