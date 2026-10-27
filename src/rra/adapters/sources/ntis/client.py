"""NTIS 국가R&D OpenAPI — 과제검색(SourcePort)·공용 호출부.

rndopen apprvKey 방식. 형식은 2026-10-27 실응답(tests/fixtures/ntis/)으로 확정: 응답 루트 RESULT
(xsi:noNamespaceSchemaLocation 속성, 네임스페이스 없음), 총건수 TOTALHITS, 레코드 RESULTSET/HIT(NO).
공개 매뉴얼(2021)과 같다.

응답 형식 두 가지 (`parse_response`):
- Accept 에 `application/json` 이 있으면 서버가 **XML 전체를 JSON 문자열 하나로 감싸** 돌려준다
  (`"<?xml …"`, content-type application/json). Accept 에 json 이 없으면 text/plain 으로 날 XML.
  오류 본문의 한글은 json Accept 가 있어야 살아오므로(없으면 "?? ?? IP? ????.") json 을 유지하고
  문자열을 푼다 — 2026-10-27 `rra sources check` 의 `XmlResponseError (ParseError)` 원인이 이것.
- 연구보고서 검색은 `DocUrl` 의 `&cn=` 처럼 맨 `&` 를 이스케이프 없이 내보낸다
  → `_xml.repair_bare_ampersands`. 강조 태그는 과제검색은 이스케이프된 꼴
  (`&lt;span class="search_word"&gt;`), 보고서는 날 `<span>` 이다.

오류는 HTTP 200 으로 온다 — 루트 `<error>문구</error>`(접근 허용 IP 아님·인증키) 또는
`<resMsg>`/`<resCd>` (URL 오류). 둘 다 NtisError 로 바꾼다(본문은 80자까지, 키 없음). IP 거부 문구는
NtisIpBlocked(SourceIpBlocked) — 호출자가 그 자료원만 건너뛴다(레인 I). record_tag 는
설정(config/sources.yaml ntis.record_tag) 필수 — 자동 탐지는 결과 1건 페이지에서 틀린다.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import SecretStr

from rra.adapters.sources import _xml
from rra.adapters.sources._base import GuardedClient, RequestBudgetExceeded
from rra.adapters.sources.ntis.projects import normalize_project
from rra.domain.models import Document
from rra.domain.rules.source_ip import SourceIpBlocked, is_ip_error

logger = logging.getLogger("rra.sources.ntis")

# Accept 에 application/json 이 있어야 오류 본문의 한글이 살아온다 (없으면 "?? ?? IP? ????.").
# 대신 정상 응답은 XML 을 JSON 문자열로 감싸 온다 → unwrap_json_string (2026-10-27 확인)
XML_TYPES = frozenset(
    {"text/xml", "application/xml", "text/html", "text/plain", "application/json"}
)
MAX_QUERY_CHARS = 200
MAX_ERROR_CHARS = 80
OK_CODES = frozenset({"0", "00", "000", "200", "SUCCESS", "OK"})
_ERROR = re.compile(r"<error>\s*(.*?)\s*</error>", re.S | re.I)
_RES_MSG = re.compile(r"<resMsg>\s*(.*?)\s*</resMsg>", re.S | re.I)
_RES_CD = re.compile(r"<resCd>\s*(.*?)\s*</resCd>", re.S | re.I)
_TAG = re.compile(r"<[^>]{1,100}>")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class NtisError(RuntimeError):
    """API 가 오류를 돌려줬다. 메시지에는 짧은 문구·코드만 (키·URL 없음)."""


class NtisIpBlocked(NtisError, SourceIpBlocked):
    """`<error>접근 허용 IP가 아닙니다.</error>` — 활용신청의 서버 IP 와 현재 공인 IP 가 다르다.
    유스케이스는 SourceIpBlocked 로 잡아 이 자료원만 건너뛴다."""


def error_message(body: bytes) -> str | None:
    """오류 본문이면 짧은 문구, 아니면 None. 파싱 전에 본다 (오류 본문은 선언 인코딩과 다를 때가
    있다)."""
    text = body[:2000].decode("utf-8", "replace").lstrip("﻿")
    m = _ERROR.search(text)
    if m:
        return _clean(m.group(1)) or "error"
    m = _RES_MSG.search(text)
    if m:
        code = _RES_CD.search(text)
        msg = _clean(m.group(1))
        return f"{msg} (resCd={_clean(code.group(1))[:10]})" if code else msg
    return None


def _clean(text: str) -> str:
    return " ".join(_CONTROL.sub(" ", _TAG.sub("", text)).split())[:MAX_ERROR_CHARS]


def unwrap_json_string(body: bytes) -> bytes:
    """`"<?xml …"` 처럼 본문 전체가 JSON 문자열 하나면 그 안의 텍스트(UTF-8)를 돌려준다.
    아니면 그대로.

    NTIS 는 Accept 에 application/json 이 있으면 XML·JSON 응답을 한 번 더 JSON 문자열로 감싼다
    (연관콘텐츠는 JSON 객체가 문자열 안에 들어 있다). 문자열이 아닌 JSON(객체·배열)은 그대로.
    """
    head = body[:4].lstrip(b"\xef\xbb\xbf \t\r\n")
    if not head.startswith(b'"'):
        return body
    try:
        inner = json.loads(body)
    except ValueError:
        return body
    return inner.encode("utf-8") if isinstance(inner, str) else body


def parse_response(body: bytes) -> Any:
    """NTIS XML 본문 → 요소 트리: JSON 문자열 풀기 → 맨 `&` 복구 → defusedxml (DTD 금지)."""
    return _xml.parse(_xml.repair_bare_ampersands(unwrap_json_string(body)))


class NtisClient:
    """호출 공통부 — 키를 붙여 GET, 오류 본문 판별, XML 파싱. 서비스별 소스가 조합한다."""

    def __init__(self, client: GuardedClient, *, apprv_key: SecretStr, base_url: str):
        self.client = client
        self._key = apprv_key
        self.base_url = base_url.rstrip("/")

    def url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    async def aclose(self) -> None:
        await self.client.aclose()

    async def get_xml(self, path: str, params: Mapping[str, str]) -> Any:
        body = await self.get_body(path, params, accept_types=XML_TYPES)
        root = parse_response(body)
        code = _xml.first_text(root, "ERROR_CODE", "errorCode", "RESULT_CODE", "resultCode")
        if code and code.upper() not in OK_CODES:
            raise NtisError(f"NTIS 오류 (code={code[:20]})")
        return root

    async def get_body(
        self, path: str, params: Mapping[str, str], *, accept_types: frozenset[str]
    ) -> bytes:
        query = {"apprvKey": self._key.get_secret_value(), **params}
        body = unwrap_json_string(
            await self.client.get_bytes(self.url(path), query, accept_types=accept_types)
        )
        message = error_message(body)
        if message is not None:
            if is_ip_error(message):
                raise NtisIpBlocked(f"NTIS 오류: {message}")
            raise NtisError(f"NTIS 오류: {message}")
        return body


def total_hits(root: Any) -> int:
    text = _xml.first_text(root, "TOTALHITS", "totalCount", "TotalCount", "TOTAL_COUNT")
    return int(text) if text.isdigit() else 0


def probe_result(root: Any, record_tag: str | None) -> dict[str, Any]:
    """`rra sources check` 결과 — 총건수·레코드 태그 후보(본문·키 없음). 자동 탐지는 자식을 가진
    형제가 가장 많은 묶음을 고르므로 과제검색에서는 NAVIGATIONENTRY(13) 가 HIT(≤10) 를 이긴다 →
    설정된 record_tag 가 응답에 있으면 후보에 넣고 `record_tag_matches`·`hits` 로 알린다."""
    candidates = {_xml.local(r.tag) for r in _xml.find_records(root)}
    out: dict[str, Any] = {"total": total_hits(root) or None}
    if record_tag:
        hits = len(_xml.find_records(root, record_tag))
        if hits:
            candidates.add(record_tag)
        out["hits"] = hits
        out["record_tag_matches"] = hits > 0
    out["record_tag_candidates"] = sorted(candidates)
    return out


class NtisProjectSource:
    """과제검색(public_project). overlap_check(기수행 국가R&D 과제 중복)의 핵심 자료원."""

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
        per_query_limit: int | None = None,
    ):
        self.api = NtisClient(client, apprv_key=apprv_key, base_url=base_url)
        self.path = project_path
        self.queries = queries
        self.institutions = list(institutions)
        self.search_field = search_field if search_field.isalnum() else "BI"
        self.display_count = max(1, min(display_count, 100))
        self.record_tag = record_tag or None
        self.per_query_limit = per_query_limit

    def __repr__(self) -> str:
        return "NtisProjectSource()"

    @property
    def client(self) -> GuardedClient:
        return self.api.client

    @property
    def url(self) -> str:
        return self.api.url(self.path)

    async def aclose(self) -> None:
        await self.api.aclose()

    async def search(self, query: str | None, limit: int) -> list[dict[str, Any]]:
        if not self.record_tag:
            raise NtisError(
                "config/sources.yaml ntis.record_tag 가 비어 있습니다 — "
                "rra sources check 로 후보를 확인해 설정하세요."
            )
        if limit <= 0:
            return []
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for q in [query] if query else list(self.queries):
            start, taken = 1, 0
            while len(out) < limit and (
                self.per_query_limit is None or taken < self.per_query_limit
            ):
                try:
                    records, total = await self._page(q, start)
                except RequestBudgetExceeded:
                    logger.warning("ntis.budget_exhausted collected=%d", len(out))
                    return out[:limit]
                for r in records:
                    key = r.get("ProjectNumber", "")
                    if key and key in seen:
                        continue  # 질의가 겹치면 같은 과제가 다시 온다
                    seen.add(key)
                    out.append(r)
                    taken += 1
                start += self.display_count
                if len(records) < self.display_count or start > total:
                    break
        return out[:limit]

    async def probe(self) -> dict[str, Any]:
        """연결 확인 1회 (rra sources check). 총건수와 레코드 태그 후보. 본문·키 없음."""
        root = await self._fetch_root(self.queries[0] if self.queries else "철도", 1, count=5)
        return probe_result(root, self.record_tag)

    async def _page(self, query: str, start: int) -> tuple[list[dict[str, Any]], int]:
        root = await self._fetch_root(query, start, count=self.display_count)
        records = [_xml.flatten(r) for r in _xml.find_records(root, self.record_tag)]
        return records, total_hits(root)

    async def _fetch_root(self, query: str, start: int, *, count: int) -> Any:
        return await self.api.get_xml(
            self.path,
            {
                "collection": "project",
                "SRWR": query.strip()[:MAX_QUERY_CHARS],
                "searchFd": self.search_field,
                "startPosition": str(start),
                "displayCnt": str(count),
            },
        )

    def normalize(self, raw: dict[str, Any]) -> Document:
        return normalize_project(raw, self.institutions)
