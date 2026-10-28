"""[4] 실시간 검색 어댑터 (LiveSourcePort) — 기존 자료원 어댑터를 감싼다 (ADR 0031).

- 네트워크·정규화는 기존 어댑터 그대로(GuardedClient 허용목록 C, normalize 순수 함수, 사람 이름
미저장).
- 실시간 전용 인스턴스(조립이 따로 만든다)라 야간 적재의 요청 예산과 섞이지 않는다. 세션마다
  요청 수를 처음부터 세고(`max_requests`), 같은 자료원에 동시에 두 세션이 들어오면 자물쇠로 줄을
  세워 자료원별 호출 간격(rate_limit)을 지킨다.
- 질의는 앞에서부터 보내고 limit 건이 차면 뒤 질의는 보내지 않는다. 같은 문서는 한 번만.
- ScienceON: 논문·보고서·특허 target 마다 limit/target 수. NTIS: 과제 절반·연구보고서 절반을 동시에.
  OpenAlex: 영문 질의, 초록 있는 것만.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Callable, Iterable
from typing import Any

from rra.adapters.sources._base import GuardedClient
from rra.domain.models import Document
from rra.domain.rules.source_ip import SourceIpBlocked

logger = logging.getLogger("rra.sources.live")


def _normalized(raws: Iterable[dict[str, Any]], normalize: Callable[[dict[str, Any]], Document]):
    for raw in raws:
        try:
            yield normalize(raw)
        except ValueError:  # 깨진 레코드 하나는 건너뛴다 (pydantic ValidationError 포함)
            continue


def _add(out: dict[str, Document], docs: Iterable[Document], limit: int) -> None:
    for d in docs:
        if len(out) >= limit:
            return
        out.setdefault(d.doc_id, d)


class _Budget:
    """세션 하나의 요청 상한 — 클라이언트 카운터를 0 으로 되돌리고 상한을 건다."""

    def __init__(self, clients: list[GuardedClient], max_requests: int):
        self.clients = clients
        self.max_requests = max(1, int(max_requests))
        self.lock = asyncio.Lock()

    def reset(self) -> None:
        for c in self.clients:
            c.requests_made = 0
            c.max_requests = self.max_requests


class LiveScienceOn:
    source = "scienceon"
    lang = "ko"

    def __init__(self, inner: Any, *, max_requests: int = 8):
        self.inner = inner  # ScienceOnSource (TokenManager 가 같은 client 를 쓴다)
        self._budget = _Budget([inner.client], max_requests)

    def __repr__(self) -> str:
        return "LiveScienceOn()"

    async def fetch(self, queries: list[str], limit: int) -> list[Document]:
        if limit <= 0 or not queries:
            return []
        per_target = max(1, math.ceil(limit / max(1, len(self.inner.targets))))
        async with self._budget.lock:
            self._budget.reset()
            self.inner.row_count = min(100, per_target)
            self.inner.per_query_limit = per_target
            out: dict[str, Document] = {}
            for q in queries:
                raws = await self.inner.search(q, limit)
                _add(out, _normalized(raws, self.inner.normalize), limit)
                if len(out) >= limit:
                    break
        return list(out.values())


class LiveNtis:
    """과제검색(→ ② 유사과제 후보) + 연구보고서(→ 관련 연구·섹션 근거). 둘 다 IP 거부면 올린다."""

    source = "ntis"
    lang = "ko"

    def __init__(self, projects: Any, reports: Any | None = None, *, max_requests: int = 6):
        self.projects = projects  # NtisProjectSource
        self.reports = reports  # NtisReportSource (없으면 과제만)
        clients = [projects.api.client] + ([reports.api.client] if reports is not None else [])
        self._budget = _Budget(clients, max_requests)

    def __repr__(self) -> str:
        return "LiveNtis()"

    async def fetch(self, queries: list[str], limit: int) -> list[Document]:
        if limit <= 0 or not queries:
            return []
        services = [self.projects] + ([self.reports] if self.reports is not None else [])
        shares = [math.ceil(limit / len(services))] * len(services)
        shares[-1] = max(0, limit - sum(shares[:-1]))
        async with self._budget.lock:
            self._budget.reset()
            found = await asyncio.gather(
                *(self._one(svc, queries, n) for svc, n in zip(services, shares, strict=True)),
                return_exceptions=True,
            )
        docs: list[Document] = []
        errors: list[BaseException] = []
        for item in found:
            if isinstance(item, BaseException):
                errors.append(item)
            else:
                docs.extend(item)
        blocked = next((e for e in errors if isinstance(e, SourceIpBlocked)), None)
        if blocked is not None:
            raise blocked
        if errors and not docs:
            raise errors[0]
        for e in errors:
            logger.warning("live.ntis_service_failed err=%s", type(e).__name__)
        return docs

    @staticmethod
    async def _one(svc: Any, queries: list[str], n: int) -> list[Document]:
        if n <= 0:
            return []
        svc.display_count = max(1, min(100, n))
        svc.per_query_limit = n
        out: dict[str, Document] = {}
        for q in queries:
            _add(out, _normalized(await svc.search(q, n), svc.normalize), n)
            if len(out) >= n:
                break
        return list(out.values())


class LiveOpenAlex:
    source = "openalex"
    lang = "en"

    def __init__(self, inner: Any, *, max_requests: int = 3):
        self.inner = inner  # OpenAlexSource
        self._budget = _Budget([inner.client], max_requests)

    def __repr__(self) -> str:
        return "LiveOpenAlex()"

    async def fetch(self, queries: list[str], limit: int) -> list[Document]:
        if limit <= 0 or not queries:
            return []
        async with self._budget.lock:
            self._budget.reset()
            self.inner.per_page = max(1, min(200, limit))
            out: dict[str, Document] = {}
            for q in queries:
                raws = await self.inner.search_query(q, limit, require_abstract=True)
                _add(out, _normalized(raws, self.inner.normalize), limit)
                if len(out) >= limit:
                    break
        return list(out.values())
