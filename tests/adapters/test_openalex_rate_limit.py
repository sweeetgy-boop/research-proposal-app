"""OpenAlex 2026-11-09 실응답 fixture — 비둘기 질의(works_pigeon.json, 이름 제거)·익명 429
(rate_limited_429.json).

저장 자료(야간 적재, 질의 목록) 경로와 실시간(LiveOpenAlex) 경로 둘 다 본다. 네트워크 없음.
운영 오류(2026-11-05 `live.source_failed source=openalex err=RateLimited`)의 원인 = 익명 검색 제한.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from rra.adapters.sources._base import GuardedClient, RateLimited
from rra.adapters.sources.live import LiveOpenAlex
from rra.adapters.sources.openalex import OpenAlexSource, normalize_work
from rra.domain.rules.source_limits import SourceRateLimited

FIXTURES = Path(__file__).parents[1] / "fixtures" / "openalex"
PIGEON = json.loads((FIXTURES / "works_pigeon.json").read_text(encoding="utf-8"))
RATE_LIMITED = json.loads((FIXTURES / "rate_limited_429.json").read_text(encoding="utf-8"))


async def _no_sleep(_):
    return None


def _429(retry_after: str | None = None):
    return httpx.Response(
        429,
        json=RATE_LIMITED["body"],
        headers={"retry-after": retry_after or RATE_LIMITED["headers"]["retry-after"]},
    )


def _client(handler, *, sleep=_no_sleep, **kw):
    """조립(_guarded)과 같은 기본값 — 재시도 3·대기 상한 60(sources.yaml max_backoff_sec)."""
    base = {"retries": 3, "max_backoff_sec": 60}
    return GuardedClient(
        ["api.openalex.org"],
        transport=httpx.MockTransport(handler),
        resolver=lambda h: False,
        sleep=sleep,
        **{**base, **kw},
    )


# ── normalize (순수 함수) ─────────────────────────────────
def test_pigeon_fixture_normalizes_every_record_with_venue_and_abstract():
    docs = [normalize_work(r) for r in PIGEON["results"]]
    assert len(docs) == len(PIGEON["results"]) == 12
    assert len({d.doc_id for d in docs}) == 12
    assert all(d.abstract for d in docs)  # has_abstract:true 필터
    assert all(d.lang == "en" and d.text_basis == "abstract" for d in docs)
    first = docs[0]
    assert first.title.startswith("Visual deterrents and physical barriers as non-let")
    assert first.raw["venue"] == "SpringerPlus"  # 유추 검색의 분야 표시(ADR 0057)
    assert first.raw["field"] is None  # 실시간 질의는 분야 목록 밖
    assert first.source == "openalex" and first.doc_type == "paper"


def test_pigeon_fixture_has_no_person_names():
    assert "NAME-REMOVED" in json.dumps(PIGEON, ensure_ascii=False)
    docs = [normalize_work(r) for r in PIGEON["results"]]
    assert all(a.startswith("NAME-REMOVED") for d in docs for a in d.authors)


def test_429_fixture_is_the_anonymous_limit():
    body = RATE_LIMITED["body"]
    assert RATE_LIMITED["status"] == 429 and body["retryAfter"] == 30
    assert "Anonymous search" in body["message"] and "API key" in body["message"]


# ── 저장 자료(야간 적재) 경로 ──────────────────────────────
async def test_ingest_path_waits_retry_after_30_then_continues():
    calls: list[int] = []
    sleeps: list[float] = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return _429()
        return httpx.Response(200, json={"results": PIGEON["results"][:3]})

    async def sleep(sec):
        sleeps.append(sec)

    src = OpenAlexSource(
        _client(handler, sleep=sleep),
        queries=[{"field": "시험", "query": "bird deterrent"}],
        per_query_limit=3,
    )
    raws = await src.search(None, 3)
    assert len(raws) == 3 and sleeps == [30.0] and len(calls) == 2
    assert all(r["_field"] == "시험" for r in raws)


async def test_ingest_path_gives_up_after_retries_as_rate_limited():
    calls: list[int] = []

    def handler(request):
        calls.append(1)
        return _429()

    src = OpenAlexSource(_client(handler), queries=[{"field": "시험", "query": "bird"}])
    with pytest.raises(RateLimited, match="재시도 3회 소진"):
        await src.search(None, 10)
    assert len(calls) == 4


# ── 실시간(LiveOpenAlex) 경로 ────────────────────────────
async def test_live_anonymous_429_fails_fast_with_key_notice():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return _429()

    client = _client(handler)
    live = LiveOpenAlex(OpenAlexSource(client), max_requests=5)
    assert client.max_backoff_sec == 5.0  # Retry-After 30 은 기다리지 않는다
    with pytest.raises(SourceRateLimited) as info:
        await live.fetch(["pigeon deterrent", "bird control"], 30)
    assert len(seen) == 1  # 재시도·다음 질의 없음
    msg = str(info.value)
    assert "OpenAlex" in msg and "익명" in msg and "RRA_OPENALEX_API_KEY" in msg
    assert "http" not in msg  # URL·키 없음


async def test_live_with_api_key_429_notice_does_not_ask_for_key():
    client = _client(lambda request: _429())
    live = LiveOpenAlex(OpenAlexSource(client, api_key=SecretStr("OA-SECRET")), max_requests=3)
    with pytest.raises(SourceRateLimited) as info:
        await live.fetch(["pigeon deterrent"], 30)
    assert "익명" not in str(info.value) and "OA-SECRET" not in str(info.value)


async def test_live_keeps_docs_from_earlier_queries_when_a_later_query_is_limited():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(200, json={"results": PIGEON["results"][:4]})
        return _429()

    live = LiveOpenAlex(OpenAlexSource(_client(handler)), max_requests=5)
    docs = await live.fetch(["pigeon deterrent", "bird control"], 30)
    assert len(docs) == 4 and len(seen) == 2  # 첫 질의 결과는 살리고 둘째 질의에서 멈춘다


async def test_live_short_retry_after_is_still_honoured():
    sleeps: list[float] = []

    async def sleep(sec):
        sleeps.append(sec)

    calls: list[int] = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return _429("2")
        return httpx.Response(200, json={"results": PIGEON["results"][:2]})

    live = LiveOpenAlex(OpenAlexSource(_client(handler, sleep=sleep)), max_requests=5)
    assert len(await live.fetch(["pigeon deterrent"], 30)) == 2 and sleeps == [2.0]


async def test_live_real_page_normalizes_without_names():
    live = LiveOpenAlex(
        OpenAlexSource(_client(lambda r: httpx.Response(200, json=PIGEON))), max_requests=3
    )
    docs = await live.fetch(["pigeon deterrent non-lethal bird control"], 40)
    assert len(docs) == 12 and all(d.source == "openalex" for d in docs)
    assert all(a.startswith("NAME-REMOVED") for d in docs for a in d.authors)
