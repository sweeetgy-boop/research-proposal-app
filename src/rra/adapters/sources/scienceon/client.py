"""ScienceON 수집 — SourcePort. 국내 논문(ARTI)·보고서(REPORT) 메타데이터.

레이트리밋 (429 이력):
- GuardedClient: 최소 간격(rate_limit, 기본 초당 1회), 429 재시도,
  Retry-After 가 상한보다 길면 즉시 RateLimited, run 당 요청 예산(max_requests, 토큰 요청 포함).
- 이 어댑터: RateLimited 가 연속 N회면 이 run 에서 수집 중단(차단기).
  예산을 다 쓰면 모은 만큼만 돌려준다.
- 순차 실행(동시성 1). 레이트 상태는 프로세스 안에만 있다 — ingest 는 한 번에 하나.

응답 형식(가이드 기준, 첫 실응답으로 확인): MetaData / resultSummary / TotalCount,
recordList / record / item[@metaCode]. 본문 오류 코드는 errorCode 요소로 온다고 가정한다.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from rra.adapters.sources import _xml
from rra.adapters.sources._base import GuardedClient, RateLimited, RequestBudgetExceeded
from rra.adapters.sources.scienceon.auth import TokenManager
from rra.adapters.sources.scienceon.normalize import normalize_record
from rra.domain.models import Document

logger = logging.getLogger("rra.sources.scienceon")

XML_TYPES = frozenset({"text/xml", "application/xml", "text/html", "text/plain"})
TOKEN_EXPIRED = frozenset({"E4103"})
# 본문으로 한도 초과를 알리는 코드. 가이드에 없으므로 첫 실응답·장애 때 확인해 채운다.
RATE_LIMIT_CODES: frozenset[str] = frozenset()
MAX_QUERY_CHARS = 200


class ScienceOnError(RuntimeError):
    """API 가 오류 코드를 돌려줬다. 메시지에는 코드만."""


class ScienceOnSource:
    source = "scienceon"

    def __init__(
        self,
        client: GuardedClient,
        tokens: TokenManager,
        *,
        base_url: str,
        targets: list[str],
        queries: list[str],
        search_field: str = "BI",
        row_count: int = 50,
        max_consecutive_429: int = 2,
    ):
        self.client = client
        self.tokens = tokens
        self.base_url = base_url.rstrip("/")
        self.targets = [t for t in targets if t.isalnum()]
        self.queries = queries
        self.search_field = search_field if search_field.isalnum() else "BI"
        self.row_count = max(1, min(row_count, 100))
        self.max_consecutive_429 = max(1, max_consecutive_429)

    def __repr__(self) -> str:
        return f"ScienceOnSource(targets={self.targets!r})"

    async def aclose(self) -> None:
        await self.client.aclose()

    async def search(self, query: str | None, limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        queries = [query] if query else list(self.queries)
        out: list[dict[str, Any]] = []
        strikes = 0
        for q in queries:
            for target in self.targets:
                page = 1
                while len(out) < limit:
                    try:
                        records, total = await self._page(target, q, page)
                    except RequestBudgetExceeded:
                        logger.warning("scienceon.budget_exhausted collected=%d", len(out))
                        return out[:limit]
                    except RateLimited:
                        strikes += 1
                        logger.warning("scienceon.rate_limited strikes=%d", strikes)
                        if strikes >= self.max_consecutive_429:
                            raise  # 차단기: 이 run 에서는 더 두드리지 않는다
                        break  # 다음 target/질의로
                    strikes = 0
                    out.extend(records)
                    if len(records) < self.row_count or page * self.row_count >= total:
                        break
                    page += 1
        return out[:limit]

    async def probe(self) -> dict[str, Any]:
        """연결 확인 (rra sources check): 토큰 발급 + target 별 1건 조회. 총건수만 돌려준다."""
        await self.tokens.token()
        totals: dict[str, int] = {}
        saved, self.row_count = self.row_count, 1
        try:
            for target in self.targets:
                _, totals[target] = await self._page(
                    target, self.queries[0] if self.queries else "철도", 1
                )
        finally:
            self.row_count = saved
        return {"auth": "ok", "totals": totals}

    async def _page(self, target: str, query: str, page: int) -> tuple[list[dict[str, Any]], int]:
        for attempt in range(2):  # 토큰 만료면 한 번 갱신 후 재시도
            params = {
                "client_id": self.tokens.client_id,
                "token": await self.tokens.token(),
                "version": "1.0",
                "action": "search",
                "target": target,
                "searchQuery": json.dumps(
                    {self.search_field: query.strip()[:MAX_QUERY_CHARS]}, ensure_ascii=False
                ),
                "curPage": str(page),
                "rowCount": str(self.row_count),
            }
            body = await self.client.get_bytes(
                f"{self.base_url}/openapicall.do", params, accept_types=XML_TYPES
            )
            root = _xml.parse(body)
            code = _xml.first_text(root, "errorCode", "error_code", "statusCode").upper()
            if code and code not in {"0", "200", "00", "SUCCESS"}:
                if code in TOKEN_EXPIRED and attempt == 0:
                    self.tokens.invalidate()
                    continue
                if code in RATE_LIMIT_CODES:
                    raise RateLimited(f"ScienceON 한도 초과 (code={code[:20]})")
                raise ScienceOnError(f"ScienceON 오류 (code={code[:20]})")
            total_text = _xml.first_text(root, "TotalCount")
            total = int(total_text) if total_text.isdigit() else 0
            records = [
                {"target": target, **_xml.flatten(r)} for r in _xml.find_records(root, "record")
            ]
            return records, total
        raise ScienceOnError("ScienceON 토큰 갱신 후에도 만료 응답")

    def normalize(self, raw: dict[str, Any]) -> Document:
        return normalize_record(raw)
