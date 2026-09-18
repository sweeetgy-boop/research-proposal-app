"""OpenAlex 어댑터 — tests/fixtures/openalex 의 실제 응답으로 검증. 네트워크 없음."""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from rra.adapters.sources import FetchError, GuardedClient, OpenAlexSource
from rra.adapters.sources.openalex import _rebuild_abstract, normalize_work

FIXTURES = Path(__file__).parents[1] / "fixtures" / "openalex"
PAGE = json.loads((FIXTURES / "works_page1.json").read_text(encoding="utf-8"))
EDGE = {
    r["id"].rsplit("/", 1)[-1]: r
    for r in json.loads((FIXTURES / "works_edge.json").read_text(encoding="utf-8"))["results"]
}


# ── normalize (순수 함수) ─────────────────────────────────
def test_normalize_real_record():
    doc = normalize_work(PAGE["results"][0])
    assert doc.doc_id == "openalex:W1966732442"
    assert doc.source == "openalex" and doc.doc_type == "paper"
    assert doc.title.startswith("Perspectives on railway track geometry condition monitoring")
    assert doc.doi == "10.1080/00423114.2015.1034730"
    assert doc.pub_date == date(2015, 4, 30)
    assert doc.lang == "en"
    assert doc.authors[:2] == ["Paul Weston", "Clive Roberts"]
    assert doc.abstract.startswith("This paper presents a view")
    assert doc.trust == "untrusted"
    assert "abstract_inverted_index" not in doc.raw
    assert doc.raw == {"openalex_id": "W1966732442", "type": PAGE["results"][0]["type"]}


def test_every_record_in_the_page_normalizes():
    docs = [normalize_work(r) for r in PAGE["results"]]
    assert len({d.doc_id for d in docs}) == len(PAGE["results"])
    assert all(d.doi and d.doi.startswith("10.") for d in docs)


def test_record_without_abstract_is_kept():
    raw = next(r for r in PAGE["results"] if not r["abstract_inverted_index"])
    doc = normalize_work(raw)
    assert doc.abstract is None and doc.title


def test_abstract_rebuild_orders_by_position():
    assert _rebuild_abstract({"world": [1], "hello": [0, 2]}) == "hello world hello"
    assert _rebuild_abstract({"x": [-1, "a"], 5: [0]}) is None
    assert _rebuild_abstract(None) is None


def test_abstract_word_count_is_capped():
    huge = {"w": list(range(100_000))}
    assert len(_rebuild_abstract(huge).split()) == 5_000


def test_null_doi():
    doc = normalize_work(EDGE["W9000000001"])
    assert doc.doi is None
    assert doc.url  # landing_page_url 로 대체


def test_missing_title_is_rejected():
    with pytest.raises(ValueError):
        normalize_work(EDGE["W9000000002"])


def test_title_control_chars_and_tags_are_stripped():
    title = normalize_work(EDGE["W9000000003"]).title
    assert "\x00" not in title and "\x1b" not in title
    assert "<i>" not in title
    assert title.startswith("Track geometry")


def test_bad_date_missing_language_and_empty_authorships():
    doc = normalize_work(EDGE["W9000000004"])
    assert doc.pub_date is None
    assert doc.lang == "und"
    assert doc.authors == []
    assert doc.url == f"https://doi.org/{doc.doi}"  # primary_location 없음 → DOI URL


@pytest.mark.parametrize("bad_id", [None, "", "https://openalex.org/A123", "W12;drop"])
def test_bad_id_is_rejected(bad_id):
    with pytest.raises(ValueError):
        normalize_work({**PAGE["results"][0], "id": bad_id})


# ── search (MockTransport) ───────────────────────────────
def page(results, cursor):
    return {"meta": {"next_cursor": cursor}, "results": results}


def source_with(handler, **kw):
    client = GuardedClient(
        ["api.openalex.org"], transport=httpx.MockTransport(handler), resolver=lambda h: False
    )
    return OpenAlexSource(client, today=lambda: date(2026, 9, 18), **kw)


async def test_search_follows_cursor_until_limit():
    results = PAGE["results"]
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        cursor = request.url.params["cursor"]
        if cursor == "*":
            return httpx.Response(200, json=page(results[:2], "c2"))
        if cursor == "c2":
            return httpx.Response(200, json=page(results[2:4], "c3"))
        return httpx.Response(200, json=page(results[4:], None))

    src = source_with(handler, per_page=2)
    out = await src.search("railway track geometry", 3)
    await src.aclose()

    assert [r["id"] for r in out] == [r["id"] for r in results[:3]]
    assert [p["cursor"] for p in seen] == ["*", "c2"]
    assert seen[0]["search"] == "railway track geometry"
    assert seen[0]["per-page"] == "2"
    assert "abstract_inverted_index" in seen[0]["select"]
    assert "filter" not in seen[0]
    assert "mailto" not in seen[0]


async def test_search_stops_when_cursor_runs_out():
    def handler(request):
        return httpx.Response(200, json=page(PAGE["results"][:2], None))

    src = source_with(handler)
    assert len(await src.search("rail", 50)) == 2
    await src.aclose()


async def test_incremental_search_uses_default_query_and_date_filter():
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=page([], None))

    src = source_with(handler, default_query="railway", lookback_days=7)
    await src.search(None, 10)
    await src.aclose()
    assert seen[0]["search"] == "railway"
    assert seen[0]["filter"] == "from_publication_date:2026-09-11"


async def test_query_is_clamped():
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=page([], None))

    src = source_with(handler, query_max_chars=10)
    await src.search("x" * 100, 5)
    await src.aclose()
    assert seen[0]["search"] == "x" * 10


async def test_zero_limit_makes_no_request():
    def handler(request):
        raise AssertionError("요청하면 안 됨")

    src = source_with(handler)
    assert await src.search("rail", 0) == []
    await src.aclose()


async def test_unexpected_shape_is_an_error():
    def handler(request):
        return httpx.Response(200, json={"error": "nope"})

    src = source_with(handler)
    with pytest.raises(FetchError):
        await src.search("rail", 5)
    await src.aclose()
