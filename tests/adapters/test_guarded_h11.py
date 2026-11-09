"""GuardedClient — httpcore 가 감싸지 않는 h11.LocalProtocolError 는 전송 오류처럼 재시도한다
(2026-11-05 운영 OpenAlex `err=LocalProtocolError` 의 재발 방지). 네트워크 없음."""

from __future__ import annotations

import h11
import httpx
import pytest

from rra.adapters.sources._base import TRANSPORT_ERRORS, FetchError, GuardedClient

OK = {"results": [], "meta": {}}


async def _no_sleep(_):
    return None


def _make(handler, **kw):
    return GuardedClient(
        ["api.openalex.org"],
        transport=httpx.MockTransport(handler),
        resolver=lambda h: False,
        sleep=_no_sleep,
        **kw,
    )


def test_h11_local_protocol_error_counts_as_transport_error():
    assert h11.LocalProtocolError in TRANSPORT_ERRORS and httpx.TransportError in TRANSPORT_ERRORS


async def test_h11_error_is_retried_then_succeeds():
    calls: list[int] = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:  # 깨진 풀 연결 — httpcore `_send_event` 는 이 예외를 감싸지 않는다
            raise h11.LocalProtocolError("Can't send data when our state is ERROR")
        return httpx.Response(200, json=OK)

    client = _make(handler)
    assert await client.get_json("https://api.openalex.org/works") == OK
    assert len(calls) == 2


async def test_h11_error_exhausted_is_a_fetch_error_naming_the_cause():
    def handler(request):
        raise h11.LocalProtocolError("Can't send data when our state is ERROR")

    client = _make(handler, retries=1)
    with pytest.raises(FetchError, match="LocalProtocolError") as info:
        await client.get_json("https://api.openalex.org/works", {"api_key": "SECRET-1"})
    assert "SECRET-1" not in str(info.value)
