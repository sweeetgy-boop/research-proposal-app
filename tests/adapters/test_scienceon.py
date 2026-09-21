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
    with pytest.raises(ValueError, match="32바이트"):
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
            if "refreshToken" in q:
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


def source_for(gw, *, targets=("ARTI",), row_count=2, max_requests=None, strikes=2):
    client = client_for(gw, max_requests=max_requests, retries=0)
    return ScienceOnSource(
        client,
        tokens_for(client),
        base_url=BASE,
        targets=list(targets),
        queries=["궤도"],
        row_count=row_count,
        max_consecutive_429=strikes,
    )


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
