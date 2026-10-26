"""KIPRIS Plus 특허·실용신안 자유검색 — SourcePort + ProbingSource.

선택 근거(2026-10-26): 공공데이터포털(data.go.kr)의 특허 API 는 KIPRIS Plus 와 같은 데이터·키 체계고
월 호출 상한 뒤에는 plus.kipris.or.kr 로 안내한다. 활용신청·키 관리·대량 호출이 KIPRIS Plus 에서
이뤄지므로 기본은 KIPRIS Plus REST(`/openapi/rest/patUtiModInfoSearchSevice/freeSearchInfo`,
키 파라미터 `accessKey`)로 한다. 경로·파라미터·레코드 태그는 config/sources.yaml 에 두어 실응답으로
바꿀 수 있다.

응답(XML): resultCode 00=정상, 20=결과 없음(빈 목록), 그 외는 오류(30 미등록 서비스, 31 키 만료).
TotalSearchCount 와 PatentUtilityInfo 레코드. 레코드 태그는 설정(기본 PatentUtilityInfo).
보안 D: 키는 요청 파라미터를 만드는 순간에만 꺼내고, 오류 메시지·로그에는 코드만.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import SecretStr

from rra.adapters.sources import _xml
from rra.adapters.sources._base import GuardedClient, RequestBudgetExceeded
from rra.adapters.sources.kipris.normalize import normalize_patent
from rra.domain.models import Document

logger = logging.getLogger("rra.sources.kipris")

XML_TYPES = frozenset({"text/xml", "application/xml", "text/html", "text/plain"})
MAX_QUERY_CHARS = 200
OK_CODES = frozenset({"00", "0", "000"})
EMPTY_CODES = frozenset({"20"})
DEFAULT_RECORD_TAG = "PatentUtilityInfo"
DEFAULT_PATH = "/openapi/rest/patUtiModInfoSearchSevice/freeSearchInfo"


class KiprisError(RuntimeError):
    """API 가 오류를 돌려줬다. 메시지에는 코드만."""


class KiprisPatentSource:
    source = "kipris"  # IngestReport 키. Document.source 는 kipris_kr

    def __init__(
        self,
        client: GuardedClient,
        *,
        access_key: SecretStr,
        base_url: str,
        queries: list[str],
        institutions: Sequence[Mapping[str, Any]],
        search_path: str = DEFAULT_PATH,
        docs_count: int = 50,
        record_tag: str = DEFAULT_RECORD_TAG,
        include_utility: bool = True,
        key_param: str = "accessKey",
    ):
        self.client = client
        self._key = access_key
        self.url = f"{base_url.rstrip('/')}/{search_path.lstrip('/')}"
        self.queries = queries
        self.institutions = list(institutions)
        self.docs_count = max(1, min(docs_count, 100))
        self.record_tag = record_tag or DEFAULT_RECORD_TAG
        self.include_utility = include_utility
        self.key_param = key_param if key_param.isidentifier() else "accessKey"

    def __repr__(self) -> str:
        return "KiprisPatentSource()"

    async def aclose(self) -> None:
        await self.client.aclose()

    async def search(self, query: str | None, limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for q in [query] if query else list(self.queries):
            start = 1
            while len(out) < limit:
                try:
                    records, total = await self._page(q, start)
                except RequestBudgetExceeded:
                    logger.warning("kipris.budget_exhausted collected=%d", len(out))
                    return out[:limit]
                for rec in records:
                    key = rec.get("ApplicationNumber") or rec.get("applicationNumber") or ""
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(rec)
                start += self.docs_count
                if len(records) < self.docs_count or start > total:
                    break
        return out[:limit]

    async def probe(self) -> dict[str, Any]:
        """연결 확인 1회 (rra sources check). 총건수와 레코드 태그 후보. 본문·키 없음."""
        root = await self._fetch_root(self.queries[0] if self.queries else "철도", 1, count=3)
        candidates = sorted({_xml.local(r.tag) for r in _xml.find_records(root)})
        total = _xml.first_text(root, "TotalSearchCount", "totalCount", "TOTAL_COUNT")
        return {
            "total": int(total) if total.isdigit() else None,
            "record_tag_candidates": candidates,
            "record_tag_matches": bool(_xml.find_records(root, self.record_tag)),
        }

    async def _page(self, query: str, start: int) -> tuple[list[dict[str, Any]], int]:
        root = await self._fetch_root(query, start, count=self.docs_count)
        total_text = _xml.first_text(root, "TotalSearchCount", "totalCount", "TOTAL_COUNT")
        total = int(total_text) if total_text.isdigit() else 0
        records = [_xml.flatten(r) for r in _xml.find_records(root, self.record_tag)]
        return records, total

    async def _fetch_root(self, query: str, start: int, *, count: int) -> Any:
        params = {
            "word": query.strip()[:MAX_QUERY_CHARS],
            "patent": "true",
            "utility": "true" if self.include_utility else "false",
            "docsStart": str(start),
            "docsCount": str(count),
            "descSort": "true",
            "sortSpec": "AD",
            self.key_param: self._key.get_secret_value(),
        }
        body = await self.client.get_bytes(self.url, params, accept_types=XML_TYPES)
        root = _xml.parse(body)
        code = _xml.first_text(root, "resultCode", "RESULT_CODE", "errorCode")
        if code and code not in OK_CODES:
            if code in EMPTY_CODES:
                return root  # 결과 없음 — 레코드가 없을 뿐
            raise KiprisError(f"KIPRIS 오류 (code={code[:20]})")
        return root

    def normalize(self, raw: dict[str, Any]) -> Document:
        return normalize_patent(raw, self.institutions)
