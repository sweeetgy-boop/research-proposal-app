"""문서 단위 검색 — 위쪽 통합 검색의 "자료" 묶음과 자료 검색 화면 (2026-10-29 [UI] 레인 3).
create_app 이 register() 로 붙인다. 로직 없음(usecases/search_documents).

- GET /v1/search/docs?q=&limit=&sources=a,b&year_from=&year_to=
  → {notice, docs: [{doc_id, title, source, source_label, url, year, summary, basis, live, trust}]}

공용 계정은 internal 을 뺀 저장소(PublicOnlyRepository)로 찾는다 — repo_for(request).
제목·요약은 수집 자료(비신뢰, UNTRUSTED_NOTICE). 화면은 doc_id 를 보이지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request

from rra.application.usecases.search_documents import SearchDocuments
from rra.domain.rules.trust import UNTRUSTED_NOTICE
from rra.entrypoints.views_refs import doc_hits_payload

MAX_DOC_LIMIT = 30
MIN_YEAR, MAX_YEAR = 1900, 2100


def register(
    app: FastAPI,
    *,
    api_version: str,
    repo_for: Callable[[Request], Any],
    clean: Callable[[str], str],
    known_sources: Iterable[str],
    query_max_chars: int,
) -> None:
    V = api_version
    known = frozenset(known_sources)

    @app.get(f"/{V}/search/docs")
    async def search_docs_route(
        request: Request,
        q: str = Query(min_length=1),
        limit: int = Query(default=5, ge=1, le=MAX_DOC_LIMIT),
        sources: str | None = Query(default=None, max_length=400),
        year_from: int | None = Query(default=None, ge=MIN_YEAR, le=MAX_YEAR),
        year_to: int | None = Query(default=None, ge=MIN_YEAR, le=MAX_YEAR),
    ) -> dict[str, Any]:
        query = q.strip()
        if not query:
            raise HTTPException(422, "검색어가 비어 있습니다.")
        if len(query) > query_max_chars:
            raise HTTPException(422, f"검색어 길이 {len(query)} > 상한 {query_max_chars}")
        picked = [s.strip() for s in (sources or "").split(",") if s.strip()]
        unknown = [s for s in picked if s not in known]
        if unknown:
            raise HTTPException(422, "모르는 자료원이 있습니다.")
        if year_from is not None and year_to is not None and year_from > year_to:
            raise HTTPException(422, "시작 연도가 끝 연도보다 늦습니다.")
        hits = await SearchDocuments(repo_for(request))(
            query, limit=limit, sources=picked or None, year_from=year_from, year_to=year_to
        )
        return {"notice": UNTRUSTED_NOTICE, "docs": doc_hits_payload(hits, clean=clean)}
