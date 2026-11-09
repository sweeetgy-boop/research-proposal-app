"""실시간 검색 — 자료원 호출 제한(SourceRateLimited, OpenAlex 익명 429)은 기다리지 않고 그
자료원만 error + 안내로 남기고 나머지 자료원은 계속한다. 새로움 확인 coverage 는 그 자료원을
`error` 로 적는다(계약 열거값). 네트워크 없음."""

from __future__ import annotations

import json
import logging

from rra.application.usecases.novelty import build_coverage
from rra.domain.rules.source_limits import (
    OPENALEX_KEY_ENV,
    SourceRateLimited,
    rate_limit_notice,
)
from tests.application.test_live_search import FakeSource, _live, _req, _three


def test_rate_limit_notice_text():
    anon = rate_limit_notice("OpenAlex", anonymous=True, key_env=OPENALEX_KEY_ENV)
    assert "OpenAlex" in anon and "RRA_OPENALEX_API_KEY" in anon and "익명" in anon
    plain = rate_limit_notice("OpenAlex")
    assert "OpenAlex" in plain and "API 키" not in plain
    assert issubclass(SourceRateLimited, RuntimeError)


async def test_rate_limited_source_is_error_with_notice_and_others_continue(caplog):
    notice = rate_limit_notice("OpenAlex", anonymous=True, key_env=OPENALEX_KEY_ENV)
    limited = FakeSource("openalex", "en", error=SourceRateLimited(notice))
    live = _live(_three(openalex=limited))
    with caplog.at_level(logging.WARNING, logger="rra.live_search"):
        summary = await live.prepare("u1", _req())
    by = {r.source: r for r in summary.sources}
    assert by["openalex"].status == "error" and by["openalex"].notice == notice
    assert by["openalex"].seconds < 1.0  # 기다리지 않았다
    assert "scienceon:A1" in summary.doc_ids and "ntis:P1" in summary.doc_ids
    assert summary.status == "partial"
    assert any("live.rate_limited source=openalex" in r.getMessage() for r in caplog.records)
    assert "http" not in json.dumps(summary.payload(), ensure_ascii=False)


async def test_rate_limited_source_shows_as_error_in_novelty_coverage():
    notice = rate_limit_notice("OpenAlex", anonymous=True, key_env=OPENALEX_KEY_ENV)
    live = _live(_three(openalex=FakeSource("openalex", "en", error=SourceRateLimited(notice))))
    summary = await live.prepare("u1", _req())
    cov = build_coverage(["own"], summary, live_sources=["scienceon", "ntis", "openalex"])
    assert cov.live is True and set(cov.searched) == {"own", "scienceon", "ntis"}
    assert cov.unavailable == [{"source": "openalex", "status": "error"}]
