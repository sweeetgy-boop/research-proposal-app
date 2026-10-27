"""ScienceON — 인증(암호화·토큰 수명)·수집(페이지·예산·429 차단기). 키·네트워크 없음.

전송 계층만 합성(MockTransport). 레코드 필드 매핑은 실응답 fixture 로 확인한다
(tests/adapters/test_real_source_fixtures.py).
"""

import base64
import json
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr

from rra.adapters.sources._base import GuardedClient, RateLimited
from rra.adapters.sources.scienceon import ScienceOnSource, TokenManager, encrypt_accounts
from rra.adapters.sources.scienceon.auth import (
    FIXED_IV,
    ScienceOnAuthError,
    normalize_mac,
)
from rra.adapters.sources.scienceon.client import ScienceOnError
from rra.adapters.sources.scienceon.normalize import normalize_record

BASE = "https://apigateway.kisti.re.kr"
KEY = "0123456789abcdef0123456789abcdef"  # 32바이트 테스트 키 (실제 키 아님)
MAC = "aa:bb:cc:dd:ee:ff"
SECRETS = ("CLIENT-XYZ", KEY, "AA-BB-CC-DD-EE-FF", "ACCESS-1", "REFRESH-1")


def decrypt(accounts: str) -> dict:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    raw = base64.urlsafe_b64decode(accounts)
    dec = Cipher(algorithms.AES(KEY.encode()), modes.CBC(FIXED_IV)).decryptor()
    padded = dec.update(raw) + dec.finalize()
    unpad = padding.PKCS7(128).unpadder()
    return json.loads(unpad.update(padded) + unpad.finalize())


# ── accounts 암호화 (순수) ────────────────────────────────
@pytest.mark.parametrize("mac", ["aa:bb:cc:dd:ee:ff", "AA-BB-CC-DD-EE-FF", "aabbccddeeff"])
def test_mac_normalized(mac):
    assert normalize_mac(mac) == "AA-BB-CC-DD-EE-FF"


@pytest.mark.parametrize("mac", ["AA-BB-CC-DD-EE", "AA:BB-CC:DD-EE:FF", "GG-BB-CC-DD-EE-FF", ""])
def test_bad_mac_rejected(mac):
    with pytest.raises(ValueError):
        normalize_mac(mac)


def test_accounts_roundtrip_and_format():
    enc = encrypt_accounts(KEY, MAC, datetime(2026, 9, 18, 14, 5, 9))
    assert decrypt(enc) == {"datetime": "20260918140509", "mac_address": "AA-BB-CC-DD-EE-FF"}
    assert enc == encrypt_accounts(KEY, MAC, datetime(2026, 9, 18, 14, 5, 9))  # IV 고정 → 결정적
    assert "+" not in enc and "/" not in enc  # URL-safe base64


def test_auth_key_must_be_32_bytes():
    with pytest.raises(ValueError, match="32자"):
        encrypt_accounts("short", MAC, datetime(2026, 1, 1))


# ── TokenManager ─────────────────────────────────────────
class Gateway:
    """토큰 발급·갱신·조회를 흉내 내는 MockTransport 핸들러. 요청을 기록한다."""

    def __init__(self, pages=None, *, refresh_ok=True, issue_error=None):
        self.requests: list[httpx.Request] = []
        self.pages = list(pages or [])
        self.refresh_ok = refresh_ok
        self.issue_error = issue_error
        self.n_issue = 0

    def __call__(self, request):
        self.requests.append(request)
        path = request.url.path
        q = {k: v[0] for k, v in parse_qs(urlsplit(str(request.url)).query).items()}
        if path == "/tokenrequest.do":
            if self.issue_error:
                return httpx.Response(200, json={"errorCode": self.issue_error})
            if "refresh_token" in q:  # 가이드: 재발급 파라미터 이름은 refresh_token
                if not self.refresh_ok:
                    return httpx.Response(200, json={"errorCode": "E4104"})
                return httpx.Response(200, json={"access_token": "ACCESS-R"})
            self.n_issue += 1
            return httpx.Response(
                200, json={"access_token": f"ACCESS-{self.n_issue}", "refresh_token": "REFRESH-1"}
            )
        item = self.pages.pop(0)
        if isinstance(item, httpx.Response):
            return item
        return httpx.Response(200, content=item.encode(), headers={"content-type": "text/xml"})


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def client_for(handler, **kw):
    async def no_sleep(_):
        return None

    return GuardedClient(
        ["apigateway.kisti.re.kr"],
        transport=httpx.MockTransport(handler),
        resolver=lambda host: False,
        sleep=no_sleep,
        **kw,
    )


def tokens_for(client, clock=None):
    return TokenManager(
        client,
        BASE,
        client_id=SecretStr("CLIENT-XYZ"),
        auth_key=SecretStr(KEY),
        mac=SecretStr(MAC),
        clock=clock or Clock(),
        now=lambda: datetime(2026, 9, 18, 14, 0, 0),
    )


async def test_token_issued_once_then_reused():
    gw = Gateway()
    tm = tokens_for(client_for(gw))
    assert await tm.token() == "ACCESS-1"
    assert await tm.token() == "ACCESS-1"
    assert tm.issued == 1 and len(gw.requests) == 1
    q = parse_qs(urlsplit(str(gw.requests[0].url)).query)
    assert q["client_id"] == ["CLIENT-XYZ"]
    assert decrypt(q["accounts"][0])["mac_address"] == "AA-BB-CC-DD-EE-FF"


async def test_expired_access_uses_refresh_then_reissues_if_refresh_rejected():
    clock = Clock()
    gw = Gateway()
    tm = tokens_for(client_for(gw), clock)
    await tm.token()
    clock.t += 2 * 3600  # access 만료
    assert await tm.token() == "ACCESS-R" and tm.refreshed == 1

    gw.refresh_ok = False
    clock.t += 2 * 3600
    assert await tm.token() == "ACCESS-2" and tm.issued == 2  # refresh 거부 → 새로 발급


async def test_invalidate_forces_refresh():
    gw = Gateway()
    tm = tokens_for(client_for(gw))
    await tm.token()
    tm.invalidate()
    assert await tm.token() == "ACCESS-R"


async def test_token_error_message_has_code_only():
    tm = tokens_for(client_for(Gateway(issue_error="E4107")))
    with pytest.raises(ScienceOnAuthError) as info:
        await tm.token()
    assert "E4107" in str(info.value)
    assert not any(s in str(info.value) for s in SECRETS)
    assert "CLIENT-XYZ" not in repr(tm)


# ── 수집 ─────────────────────────────────────────────────
def page(n, total, start=0, code=None):
    records = "".join(
        f'<record><item metaCode="CN"><![CDATA[CN{start + i}]]></item>'
        f'<item metaCode="Title"><![CDATA[궤도 논문 {start + i}]]></item></record>'
        for i in range(n)
    )
    err = f"<errorCode>{code}</errorCode>" if code else ""
    return (
        f"<MetaData>{err}<resultSummary><TotalCount>{total}</TotalCount></resultSummary>"
        f"<recordList>{records}</recordList></MetaData>"
    )


def source_for(
    gw, *, targets=("ARTI",), row_count=2, max_requests=None, strikes=2, per_query_limit=None
):
    client = client_for(gw, max_requests=max_requests, retries=0)
    return ScienceOnSource(
        client,
        tokens_for(client),
        base_url=BASE,
        targets=list(targets),
        queries=["궤도"],
        row_count=row_count,
        max_consecutive_429=strikes,
        per_query_limit=per_query_limit,
    )


async def test_token_xml_error_body_gives_code_only():
    """복호화 실패(키·client_id 가 바뀐 경우)는 JSON 이 아니라 XML E5001 로 온다."""
    xml = (
        "<MetaData><resultSummary><statusCode>500</statusCode></resultSummary>"
        "<errorDetail><errorCode>E5001</errorCode><errorMessage>x</errorMessage></errorDetail></MetaData>"
    )

    def handler(request):
        return httpx.Response(200, content=xml.encode(), headers={"content-type": "text/xml"})

    with pytest.raises(ScienceOnAuthError, match="E5001"):
        await tokens_for(client_for(handler)).token()


async def test_refresh_uses_refresh_token_param_name():
    clock = Clock()
    gw = Gateway()
    tm = tokens_for(client_for(gw), clock)
    await tm.token()
    clock.t += 2 * 3600
    await tm.token()
    q = parse_qs(urlsplit(str(gw.requests[-1].url)).query)
    assert "refresh_token" in q and "refreshToken" not in q


async def test_search_sends_xml_accept_header():
    gw = Gateway([page(1, 1)])
    await source_for(gw).search(None, 10)
    assert "text/xml" in gw.requests[-1].headers["accept"]


async def test_per_query_limit_caps_pages_per_query_and_target():
    gw = Gateway([page(2, 10), page(2, 10, start=2), page(2, 10, start=20), page(2, 10, start=22)])
    src = source_for(gw, targets=("ARTI", "REPORT"), per_query_limit=3)
    raws = await src.search(None, 100)
    # ARTI 는 3건에서 끊고(2페이지째 1건만) REPORT 로 넘어간다. 총건수 10 이어도 더 넘기지 않는다
    assert [r["CN"] for r in raws] == ["CN0", "CN1", "CN2", "CN20", "CN21", "CN22"]
    assert len(gw.requests) == 5  # 토큰 1 + ARTI 2페이지 + REPORT 2페이지


# ── 정규화 (실응답 metaCode, tests/fixtures/scienceon 으로 확정) ─────────
def test_normalize_drops_person_names_keeps_institutions():
    doc = normalize_record(
        {
            "target": "ARTI",
            "CN": "JAKO2011",
            "Title": "궤도 논문",
            "Author": "홍길동;김철수;",
            "Affiliation": "한국철도공사 철도연구원;서울과학기술대학교 철도전문대학원",
            "Publisher": "한국철도학회",
            "Pubdate": "20110626",
            "DOI": "https://doi.org/10.7782/jksr.2011.14.3.248",
            "ContentURL": "http://click.ndsl.kr/servlet/OpenAPIDetailView?keyValue=1",
            "Lang": "한국어",
        },
        [{"tag": "korail", "name": "한국철도공사"}],
    )
    assert doc.authors == [] and "홍길동" not in str(doc.model_dump())
    assert doc.raw["orgs_named"][:2] == [
        "한국철도공사 철도연구원",
        "서울과학기술대학교 철도전문대학원",
    ]
    assert doc.orgs == ["korail"]
    assert doc.doi == "10.7782/jksr.2011.14.3.248"
    assert doc.pub_date.isoformat() == "2011-06-26" and doc.url.startswith("http://click.ndsl.kr/")
    assert doc.doc_type == "paper" and doc.lang == "ko"


def test_normalize_report_pubdate_with_zero_month_and_patent_fields():
    report = normalize_record(
        {
            "target": "REPORT",
            "CN": "TRKO2019",
            "Title": "보고서",
            "Pubdate": "20190400",
            "Pjn": "16",
        }
    )
    assert report.doc_type == "internal_report" and report.pub_date.isoformat() == "2019-04-01"
    assert report.raw["project_no"] == "16"
    patent = normalize_record(
        {
            "target": "PATENT",
            "CN": "KOR1020177029671",
            "Title": "레일 체결장치",
            "Applicants": "팬드롤 리미티드;홍길동",
            "ApplNum": "10-2017-7029671",
            "ApplDate": "20171016",
            "IPC": "E01B-001/00;E01B-029/00;",
            "PatentStatus": "등록",
            "Nation": "ko",
        }
    )
    assert patent.doc_type == "patent" and patent.application_no == "1020177029671"
    assert patent.raw["orgs_named"] == ["팬드롤 리미티드"] and "홍길동" not in str(
        patent.model_dump()
    )
    assert patent.codes == ["E01B-001/00", "E01B-029/00"] and patent.raw["status"] == "등록"
    assert patent.pub_date.isoformat() == "2017-10-16"


async def test_pages_until_total_and_sends_expected_params():
    gw = Gateway([page(2, 3), page(1, 3, start=2)])
    raws = await source_for(gw).search(None, 10)
    assert [r["CN"] for r in raws] == ["CN0", "CN1", "CN2"]
    assert raws[0]["target"] == "ARTI"
    q = parse_qs(urlsplit(str(gw.requests[1].url)).query)
    assert q["token"] == ["ACCESS-1"] and q["action"] == ["search"] and q["curPage"] == ["1"]
    assert json.loads(q["searchQuery"][0]) == {"BI": "궤도"}


async def test_budget_exhaustion_returns_partial_not_error():
    gw = Gateway([page(2, 10), page(2, 10, start=2), page(2, 10, start=4)])
    raws = await source_for(gw, max_requests=3).search(None, 10)  # 토큰 1 + 페이지 2
    assert [r["CN"] for r in raws] == ["CN0", "CN1", "CN2", "CN3"]


async def test_one_429_skips_target_two_in_a_row_stop_the_source():
    gw = Gateway([httpx.Response(429), page(1, 1)])
    raws = await source_for(gw, targets=("ARTI", "REPORT")).search(None, 10)
    assert [r["target"] for r in raws] == ["REPORT"]  # 첫 429 는 그 target 만 건너뜀

    gw = Gateway([httpx.Response(429), httpx.Response(429)])
    with pytest.raises(RateLimited):
        await source_for(gw, targets=("ARTI", "REPORT")).search(None, 10)


async def test_long_retry_after_trips_immediately_without_hammering():
    gw = Gateway([httpx.Response(429, headers={"retry-after": "3600"})])
    with pytest.raises(RateLimited):
        await source_for(gw, strikes=1).search(None, 10)
    assert len(gw.requests) == 2  # 토큰 1 + 조회 1, 재시도 없음


async def test_expired_token_code_refreshes_once_and_retries():
    gw = Gateway([page(0, 0, code="E4103"), page(1, 1)])
    raws = await source_for(gw).search(None, 10)
    assert len(raws) == 1
    q = parse_qs(urlsplit(str(gw.requests[-1].url)).query)
    assert q["token"] == ["ACCESS-R"]


async def test_other_error_code_fails_with_code_only():
    gw = Gateway([page(0, 0, code="E4006")])
    with pytest.raises(ScienceOnError, match="E4006"):
        await source_for(gw).search(None, 10)


async def test_dtd_in_response_is_rejected():
    evil = '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><MetaData>&x;</MetaData>'
    from rra.adapters.sources._xml import XmlResponseError

    with pytest.raises(XmlResponseError):
        await source_for(Gateway([evil])).search(None, 10)


async def test_search_skips_a_target_with_server_error_and_keeps_the_rest():
    """한 (target, 질의) 의 서버 오류(code=500)는 그 조합만 건너뛴다 — 모은 것은 적재한다."""
    from rra.adapters.sources.scienceon.client import ScienceOnError, ScienceOnSource

    src = object.__new__(ScienceOnSource)
    src.targets, src.queries = ["ARTI", "PATENT"], ["철도 궤도", "전차선"]
    src.per_query_limit, src.row_count, src.max_consecutive_429 = 10, 10, 2
    calls = []

    async def page(target, q, page_no):
        calls.append((target, q))
        if target == "PATENT" and q == "철도 궤도":
            raise ScienceOnError("ScienceON 오류 (code=500)")
        return [{"target": target, "CN": f"{target}-{q}"}], 1

    src._page = page
    rows = await ScienceOnSource.search(src, None, 100)
    assert [r["CN"] for r in rows] == ["ARTI-철도 궤도", "ARTI-전차선", "PATENT-전차선"]
    assert len(calls) == 4

    async def always_fail(target, q, page_no):
        raise ScienceOnError("ScienceON 오류 (code=500)")

    src._page = always_fail
    import pytest

    with pytest.raises(ScienceOnError, match="code=500"):  # 전부 실패면 첫 오류를 그대로
        await ScienceOnSource.search(src, None, 100)
