"""KIPRIS Plus 특허·실용신안 자유검색 — SourcePort + ProbingSource.

선택 근거(2026-10-26): 공공데이터포털(data.go.kr)의 특허 API 는 KIPRIS Plus 와 같은 데이터·키 체계고
월 호출 상한 뒤에는 plus.kipris.or.kr 로 안내한다. 활용신청·키 관리·대량 호출이 KIPRIS Plus 에서
이뤄지므로 기본은 KIPRIS Plus REST(`/openapi/rest/patUtiModInfoSearchSevice/freeSearchInfo`,
키 파라미터 `accessKey`)로 한다. 경로·파라미터·레코드 태그는 config/sources.yaml 에 두어 실응답으로
바꿀 수 있다.

응답(XML): resultCode 00=정상, 20=결과 없음(빈 목록), 그 외는 오류(30 미등록 서비스, 31 키 만료).
TotalSearchCount 와 PatentUtilityInfo 레코드. 레코드 태그는 설정(기본 PatentUtilityInfo).
보안 D: 키는 요청 파라미터를 만드는 순간에만 꺼내고, 오류 메시지·로그에는 코드만.

분류(IPC) 검색 — 2026-11-10 실응답으로 확정(tests/fixtures/kipris/advanced/):
같은 호스트의 항목별 검색 `/kipo-api/kipi/patUtiModInfoSearchSevice/getAdvancedSearch`,
파라미터 `ipcNumber`(예: "A01M 29/00", 서브클래스 "A01M" 도 됨)·`patent`·`utility`·`numOfRows`·
`pageNo`, 키 파라미터 `ServiceKey`(같은 키). 응답은 `response/body/items/item` 레코드(요소 이름이
소문자로 시작: applicationNumber·inventionTitle·astrtCont·ipcNumber …)와 `count/totalCount`.
freeSearchInfo 의 `word` 로는 분류 검색을 하지 않는다. 확인하지 않은 파라미터(정렬 등)는
보내지 않는다.
"""

from __future__ import annotations

import logging
import re
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
CLASS_PATH = "/kipo-api/kipi/patUtiModInfoSearchSevice/getAdvancedSearch"
CLASS_KEY_PARAM = "ServiceKey"
CLASS_RECORD_TAG = "item"
MAX_CLASS_ROWS = 100
# IPC — 서브클래스(A01M) 또는 메인그룹/서브그룹(A01M 29/00). 그 밖의 글은 보내지 않는다
_IPC = re.compile(r"^([A-H]\d{2}[A-Z])(?:\s*(\d{1,4})/(\d{1,6}))?$")


def normalize_ipc(code: str) -> str | None:
    """분류 코드 → KIPRIS 가 받는 꼴("A01M 29/00" 또는 "A01M"). 형식이 아니면 None."""
    m = _IPC.match(" ".join((code or "").upper().split()))
    if m is None:
        return None
    return f"{m.group(1)} {m.group(2)}/{m.group(3)}" if m.group(2) else m.group(1)


class KiprisError(RuntimeError):
    """API 가 오류를 돌려줬다. 메시지에는 코드만."""


def class_total(root: Any) -> int | None:
    """항목별 검색 응답의 총 건수(`count/totalCount`). 없거나 숫자가 아니면 None."""
    text = _xml.first_text(root, "totalCount", "TotalSearchCount", "TOTAL_COUNT")
    return int(text) if text.isdigit() else None


class KiprisClassCount:
    """`problem_card_contract.PatentClassCount` 구현 — KIPRIS 분류 검색 총 건수.

    일일 호출 카운터(실시간 검색과 같은 파일)를 1 쓰고, 상한을 넘었거나 실패면 None
    (예외를 올리지 않는다). 로그에는 예외 클래스명만(D)."""

    def __init__(self, source: KiprisPatentSource, *, counter: Any | None = None):
        self.source = source
        self.counter = counter

    def __repr__(self) -> str:
        return "KiprisClassCount()"

    async def __call__(self, ipc: str) -> int | None:
        if normalize_ipc(ipc) is None:
            return None
        if self.counter is not None and not self.counter.try_spend(1):
            logger.info("kipris.class_count_cap")
            return None
        try:
            # 오래 도는 프로세스에서 요청 예산(max_requests_per_run)이 쌓여 막히지 않게
            # 호출마다 0 부터 센다
            self.source.client.requests_made = 0
            return await self.source.count_class(ipc)
        except Exception as exc:  # 실패는 '확인 못 함' — 진단을 막지 않는다
            logger.warning("kipris.class_count_failed err=%s", type(exc).__name__)
            return None


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
        class_path: str = CLASS_PATH,
        class_key_param: str = CLASS_KEY_PARAM,
        class_record_tag: str = CLASS_RECORD_TAG,
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
        self.class_url = f"{base_url.rstrip('/')}/{class_path.lstrip('/')}"
        self.class_key_param = (
            class_key_param if class_key_param.isidentifier() else CLASS_KEY_PARAM
        )
        self.class_record_tag = class_record_tag or CLASS_RECORD_TAG

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

    async def search_class(self, ipc: str, limit: int) -> list[dict[str, Any]]:
        """분류(IPC) 검색 — 첫 쪽만(요청 1건), 최대 limit 건. 형식이 아닌 코드는 빈 목록."""
        code = normalize_ipc(ipc)
        if code is None or limit <= 0:
            return []
        try:
            root = await self._fetch_class(code, rows=min(MAX_CLASS_ROWS, limit))
        except RequestBudgetExceeded:
            logger.warning("kipris.budget_exhausted class_search=1")
            return []
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for rec in (_xml.flatten(r) for r in _xml.find_records(root, self.class_record_tag)):
            key = rec.get("applicationNumber") or rec.get("ApplicationNumber") or ""
            if key in seen:
                continue
            seen.add(key)
            out.append(rec)
        return out[:limit]

    async def count_class(self, ipc: str) -> int | None:
        """분류(IPC) 검색 총 건수(요청 1건). 형식이 아닌 코드·건수 칸 없음이면 None."""
        code = normalize_ipc(ipc)
        if code is None:
            return None
        return class_total(await self._fetch_class(code, rows=1))

    async def _fetch_class(self, code: str, *, rows: int) -> Any:
        params = {
            "ipcNumber": code,
            "patent": "true",
            "utility": "true" if self.include_utility else "false",
            "numOfRows": str(max(1, rows)),
            "pageNo": "1",
            self.class_key_param: self._key.get_secret_value(),
        }
        body = await self.client.get_bytes(self.class_url, params, accept_types=XML_TYPES)
        root = _xml.parse(body)
        code_text = _xml.first_text(root, "resultCode", "RESULT_CODE", "errorCode")
        if code_text and code_text not in OK_CODES and code_text not in EMPTY_CODES:
            raise KiprisError(f"KIPRIS 오류 (code={code_text[:20]})")
        return root

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
