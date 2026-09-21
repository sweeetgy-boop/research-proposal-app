"""NTIS 국가R&D 과제검색 — SourcePort. overlap_check(기수행 과제 중복)의 핵심 자료원.

rndopen apprvKey 방식. 경로·레코드 태그는 공개 페이지에 없고 매뉴얼에만 있어
config/sources.yaml 로 뺐다. 첫 실응답 fixture 로 확정한다.
record_tag 는 필수다 — 자동 탐지는 결과가 1건인 페이지에서 감싸는 요소를 레코드로 잘못 고른다
(녹화 도구가 태그 후보를 알려 준다).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import SecretStr

from rra.adapters.sources import _xml
from rra.adapters.sources._base import GuardedClient, RequestBudgetExceeded
from rra.adapters.sources.ntis.projects import normalize_project
from rra.domain.models import Document

logger = logging.getLogger("rra.sources.ntis")

XML_TYPES = frozenset({"text/xml", "application/xml", "text/html", "text/plain"})
MAX_QUERY_CHARS = 200


class NtisError(RuntimeError):
    """API 가 오류를 돌려줬다. 메시지에는 코드만."""


class NtisProjectSource:
    source = "ntis"

    def __init__(
        self,
        client: GuardedClient,
        *,
        apprv_key: SecretStr,
        base_url: str,
        project_path: str,
        queries: list[str],
        institutions: Sequence[Mapping[str, Any]],
        search_field: str = "BI",
        display_count: int = 100,
        record_tag: str | None = None,
    ):
        self.client = client
        self._key = apprv_key
        self.url = f"{base_url.rstrip('/')}/{project_path.lstrip('/')}"
        self.queries = queries
        self.institutions = list(institutions)
        self.search_field = search_field if search_field.isalnum() else "BI"
        self.display_count = max(1, min(display_count, 100))
        self.record_tag = record_tag or None

    def __repr__(self) -> str:
        return "NtisProjectSource()"

    async def aclose(self) -> None:
        await self.client.aclose()

    async def search(self, query: str | None, limit: int) -> list[dict[str, Any]]:
        if not self.record_tag:
            raise NtisError(
                "config/sources.yaml ntis.record_tag 가 비어 있습니다 — "
                "rra sources check 로 후보를 확인해 설정하세요."
            )
        if limit <= 0:
            return []
        out: list[dict[str, Any]] = []
        for q in [query] if query else list(self.queries):
            start = 1
            while len(out) < limit:
                try:
                    records, total = await self._page(q, start)
                except RequestBudgetExceeded:
                    logger.warning("ntis.budget_exhausted collected=%d", len(out))
                    return out[:limit]
                out.extend(records)
                start += self.display_count
                if len(records) < self.display_count or start > total:
                    break
        return out[:limit]

    async def probe(self) -> dict[str, Any]:
        """연결 확인 1회 (rra sources check). 총건수와 레코드 태그 후보를 돌려준다. 본문·키 없음."""
        root = await self._fetch_root(self.queries[0] if self.queries else "철도", 1, count=5)
        candidates = sorted({_xml.local(r.tag) for r in _xml.find_records(root)})
        total = _xml.first_text(root, "TOTALHITS", "totalCount", "TotalCount", "TOTAL_COUNT")
        return {
            "total": int(total) if total.isdigit() else None,
            "record_tag_candidates": candidates,
        }

    async def _page(self, query: str, start: int) -> tuple[list[dict[str, Any]], int]:
        root = await self._fetch_root(query, start, count=self.display_count)
        total_text = _xml.first_text(root, "TOTALHITS", "totalCount", "TotalCount", "TOTAL_COUNT")
        total = int(total_text) if total_text.isdigit() else 0
        records = [_xml.flatten(r) for r in _xml.find_records(root, self.record_tag)]
        return records, total

    async def _fetch_root(self, query: str, start: int, *, count: int) -> Any:
        params = {
            "apprvKey": self._key.get_secret_value(),
            "collection": "project",
            "SRWR": query.strip()[:MAX_QUERY_CHARS],
            "searchFd": self.search_field,
            "startPosition": str(start),
            "displayCnt": str(count),
        }
        body = await self.client.get_bytes(self.url, params, accept_types=XML_TYPES)
        root = _xml.parse(body)
        code = _xml.first_text(root, "ERROR_CODE", "errorCode", "RESULT_CODE", "resultCode")
        if code and code.upper() not in {"0", "00", "000", "200", "SUCCESS", "OK"}:
            raise NtisError(f"NTIS 오류 (code={code[:20]})")
        return root

    def normalize(self, raw: dict[str, Any]) -> Document:
        return normalize_project(raw, self.institutions)
