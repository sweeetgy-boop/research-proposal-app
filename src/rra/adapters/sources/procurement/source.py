"""G2bProcurementSource — 나라장터 입찰공고(용역) API → raw dict → Document (normalize 는 순수).

응답(JSON) `response.body.items[]` 의 필드 이름은 공공데이터포털 "조달청_나라장터
입찰공고정보서비스"
명세
기준이며
실응답으로 확정되기 전까지 `FIELDS` 는 후보다(ScienceON·NTIS 와 같은 절차: 키 투입 →
tests/tools/record_fixture
로
녹화 → 매핑 확정). 모르는 필드는 무시한다.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import Any

from pydantic import SecretStr

from rra.adapters.sources._base import BlockedURL, FetchError, GuardedClient
from rra.adapters.sources._orgs import org_tags
from rra.domain.models import Document
from rra.domain.rules.overlap import PROCURING_STATUS

logger = logging.getLogger("rra.sources.g2b")

# 읽는 필드만 (담당자 이름·전화·이메일 필드는 목록에 없다 — D·개인정보)
FIELDS = {
    "no": "bidNtceNo",
    "ord": "bidNtceOrd",
    "title": "bidNtceNm",
    "notice_org": "ntceInsttNm",
    "demand_org": "dminsttNm",
    "posted": "bidNtceDt",
    "close": "bidClseDt",
    "opening": "opengDt",
    "kind": "ntceKindNm",
    "contract_method": "cntrctCnclsMthdNm",
    "bid_method": "bidMethdNm",
    "service_div": "srvceDivNm",
    "price": "presmptPrce",
    "url": "bidNtceDtlUrl",
    "re_notice": "reNtceYn",
}
_SPEC_NAME = re.compile(r"^ntceSpecFileNm\d+$")
_DT = re.compile(r"(\d{4})-?(\d{2})-?(\d{2})")
PROCURED_STATUS = "procured"  # 공고일이 active_days 보다 오래됨 — 용역 발주됨(기간 경과 추정)


class G2bProcurementSource:
    """SourcePort + ProbingSource. source='g2b', doc_type='procurement'."""

    source = "g2b"

    def __init__(
        self,
        client: GuardedClient,
        *,
        service_key: SecretStr,
        base_url: str = "https://apis.data.go.kr",
        path: str = "/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch",
        queries: Sequence[str] = ("철도",),
        institutions: Sequence[Mapping[str, Any]] = (),
        org_filter: Sequence[str] = (),
        lookback_days: int = 365,
        rows: int = 100,
        max_pages: int = 5,
        active_days: int = 540,
        today: Callable[[], date] = date.today,
    ):
        self.client = client
        self._key = service_key
        self.base_url = base_url.rstrip("/")
        self.path = path
        self.queries = list(queries)
        self.institutions = list(institutions)
        self.org_filter = [o for o in org_filter if o.strip()]
        self.lookback_days = lookback_days
        self.rows = rows
        self.max_pages = max_pages
        self.active_days = active_days
        self._today = today

    def __repr__(self) -> str:
        return f"G2bProcurementSource(queries={len(self.queries)})"

    async def aclose(self) -> None:
        await self.client.aclose()

    def _params(self, query: str, page: int) -> dict[str, Any]:
        end = datetime.combine(self._today(), datetime.min.time()).replace(hour=23, minute=59)
        begin = end - timedelta(days=self.lookback_days)
        return {
            "serviceKey": self._key.get_secret_value(),
            "type": "json",
            "numOfRows": self.rows,
            "pageNo": page,
            "inqryDiv": 1,  # 공고게시일시 기준
            "inqryBgnDt": begin.strftime("%Y%m%d%H%M"),
            "inqryEndDt": end.strftime("%Y%m%d%H%M"),
            "bidNtceNm": query,
        }

    async def _page(self, query: str, page: int) -> tuple[list[dict[str, Any]], int]:
        data = await self.client.get_json(f"{self.base_url}{self.path}", self._params(query, page))
        return parse_response(data)

    async def probe(self) -> dict[str, Any]:
        items, total = await self._page(self.queries[0] if self.queries else "철도", 1)
        keys = sorted({k for it in items for k in it})
        return {"total": total, "rows": len(items), "field_candidates": keys[:60]}

    async def search(self, query: str | None, limit: int) -> list[dict[str, Any]]:
        queries = [query] if query else self.queries
        out: dict[str, dict[str, Any]] = {}
        for q in queries:
            page = 1
            while page <= self.max_pages and len(out) < limit:
                try:
                    items, total = await self._page(q, page)
                except (FetchError, BlockedURL) as exc:
                    logger.warning("g2b.page_failed error=%s page=%d", type(exc).__name__, page)
                    break
                for it in items:
                    if not self._wanted(it):
                        continue
                    key = f"{it.get(FIELDS['no'], '')}-{it.get(FIELDS['ord'], '')}"
                    out.setdefault(key, {**it, "_query": q})
                    if len(out) >= limit:
                        break
                if page * self.rows >= total or not items:
                    break
                page += 1
        return list(out.values())[:limit]

    def _wanted(self, item: Mapping[str, Any]) -> bool:
        """철도 기관(공고기관·수요기관) 공고만. org_filter 가 비면 전부."""
        if not self.org_filter:
            return True
        names = "".join(
            str(item.get(FIELDS[k]) or "") for k in ("notice_org", "demand_org")
        ).replace(" ", "")
        return any(o.replace(" ", "") in names for o in self.org_filter)

    def normalize(self, raw: dict[str, Any]) -> Document:
        return normalize_g2b_item(
            raw,
            institutions=self.institutions,
            today=self._today(),
            active_days=self.active_days,
        )


def parse_response(data: Any) -> tuple[list[dict[str, Any]], int]:
    """(items, totalCount). resultCode 가 00 이 아니면 FetchError (본문은 넣지 않는다)."""
    if not isinstance(data, dict):
        raise FetchError("g2b: JSON 객체가 아닌 응답")
    if "OpenAPI_ServiceResponse" in data:  # 게이트웨이 오류(키 없음·서비스 없음)
        code = (data["OpenAPI_ServiceResponse"].get("cmmMsgHeader") or {}).get("returnReasonCode")
        raise FetchError(f"g2b: 게이트웨이 오류 returnReasonCode={code}")
    resp = data.get("response") or {}
    header = resp.get("header") or {}
    if str(header.get("resultCode", "00")) not in ("00", "0"):
        raise FetchError(f"g2b: resultCode={header.get('resultCode')}")
    body = resp.get("body") or {}
    items = body.get("items") or []
    if isinstance(items, dict):  # {"item": [...]} 꼴
        items = items.get("item") or []
    if isinstance(items, dict):
        items = [items]
    total = body.get("totalCount") or 0
    try:
        total = int(total)
    except (TypeError, ValueError):
        total = len(items)
    return [it for it in items if isinstance(it, dict)], total


def _date(value: Any) -> date | None:
    m = _DT.search(str(value or ""))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def normalize_g2b_item(
    raw: Mapping[str, Any],
    *,
    institutions: Sequence[Mapping[str, Any]] = (),
    today: date | None = None,
    active_days: int = 540,
) -> Document:
    f = {k: str(raw.get(v) or "").strip() for k, v in FIELDS.items()}
    if not f["no"] or not f["title"]:
        raise ValueError("공고번호·공고명 없음")
    posted = _date(f["posted"])
    close = _date(f["close"])
    today = today or date.today()
    status = PROCURING_STATUS
    if posted and (today - posted).days > active_days:
        status = PROCURED_STATUS
    spec_names = [str(v) for k, v in raw.items() if _SPEC_NAME.match(k) and v]
    lines = [
        f"[발주 용역 공고] {f['title']}",
        f"공고기관: {f['notice_org'] or '-'} / 수요기관: {f['demand_org'] or '-'}",
        f"공고일: {posted.isoformat() if posted else '-'} / "
        f"입찰마감: {close.isoformat() if close else '-'}",
    ]
    if f["kind"] or f["contract_method"] or f["bid_method"]:
        lines.append(
            f"공고종류: {f['kind'] or '-'} / 계약방법: {f['contract_method'] or '-'} / "
            f"입찰방식: {f['bid_method'] or '-'}"
        )
    if f["service_div"]:
        lines.append(f"용역구분: {f['service_div']}")
    if f["price"]:
        lines.append(f"추정가격(원): {f['price']}")
    if spec_names:
        lines.append("공고서·과업 문서: " + ", ".join(spec_names[:10]))
    body = "\n".join(lines)
    ord_ = f["ord"] or "00"
    orgs = org_tags([f["notice_org"], f["demand_org"]], institutions)
    return Document(
        doc_id=f"g2b:{f['no']}-{ord_}",
        source="g2b",
        doc_type="procurement",
        title=f["title"][:300],
        abstract=body,
        body=body,
        pub_date=posted,
        orgs=orgs,
        lang="ko",
        url=f["url"] or None,
        text_basis="abstract",  # 과업 개요(공고서 첨부)는 받지 않는다 — 제목·기관·일정만
        visibility="public",
        raw={
            "bid_no": f["no"],
            "bid_ord": ord_,
            "notice_org": f["notice_org"],
            "demand_org": f["demand_org"],
            "close": close.isoformat() if close else None,
            "contract_method": f["contract_method"] or None,
            "service_div": f["service_div"] or None,
            "price": f["price"] or None,
            "spec_files": spec_names[:10],
            "status": status,
            "re_notice": f["re_notice"] or None,
            "query": raw.get("_query"),
        },
    )
