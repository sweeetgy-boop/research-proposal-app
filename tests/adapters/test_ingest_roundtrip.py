"""Step 4 완료 기준: ingest → search 왕복.

MockTransport(실제 OpenAlex 응답 fixture) → OpenAlexSource → IngestSources
→ SQLiteDocumentRepository(DeterministicEmbedding) → hybrid_search. 네트워크·모델 없음.
"""

import json
from pathlib import Path

import httpx
import pytest

from rra.adapters.persistence import SQLiteDocumentRepository
from rra.adapters.sources import GuardedClient, OpenAlexSource
from rra.application.usecases.ingest_sources import IngestSources
from tests.fakes import DeterministicEmbedding

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

PAGE = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "openalex" / "works_page1.json").read_text(
        encoding="utf-8"
    )
)


@pytest.fixture
def repo(tmp_path):
    r = SQLiteDocumentRepository(tmp_path / "rra.sqlite", DeterministicEmbedding())
    yield r
    r.close()


@pytest.fixture
async def source():
    def handler(request):
        assert request.url.host == "api.openalex.org"
        return httpx.Response(200, json={**PAGE, "meta": {**PAGE["meta"], "next_cursor": None}})

    client = GuardedClient(
        ["api.openalex.org"], transport=httpx.MockTransport(handler), resolver=lambda h: False
    )
    src = OpenAlexSource(client)
    yield src
    await src.aclose()


async def test_ingest_then_search_round_trip(source, repo):
    report = await IngestSources([source], repo)("railway track geometry")

    n = len(PAGE["results"])
    assert report.fetched == {"openalex": n}
    assert report.skipped == {"openalex": 0}
    assert report.stored == n
    assert report.chunks >= n - 1  # 초록 없는 레코드는 청크가 없다

    hits = repo.hybrid_search(["tamping degradation"], k=5)
    assert hits and hits[0].doc_id == "openalex:W2118179191"
    assert all(c.trust == "untrusted" for c in hits)

    doc = repo.get_document("openalex:W2118179191")
    assert doc.title == "The effects of tamping on railway track geometry degradation"
    assert doc.doi == "10.1177/0954409713480439"


async def test_second_ingest_is_idempotent(source, repo):
    ingest = IngestSources([source], repo)
    await ingest("railway track geometry")
    await ingest("railway track geometry")
    hits = repo.hybrid_search(["tamping degradation"], k=20)
    assert len([c for c in hits if c.doc_id == "openalex:W2118179191"]) == 1
