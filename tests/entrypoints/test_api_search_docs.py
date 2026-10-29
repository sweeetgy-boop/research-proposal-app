"""GET /v1/search/docs — 위쪽 통합 검색의 "자료" 묶음·자료 검색 화면 (2026-10-29 [UI] 레인 3).
문서 단위·표시 정보만, 자료원·연도 거르기, 공용 계정 internal 제외, 로그인 전 401."""

from __future__ import annotations

from datetime import date

from rra.domain.models import Chunk, Document
from tests.entrypoints.test_api_login import AUTH, GUEST, INTERNAL_DOC, build, client_for, login

PAPER = Document(
    doc_id="openalex:w-2021",
    source="openalex",
    doc_type="paper",
    title="궤도 틀림 열화 예측",
    abstract="궤도 틀림 열화 속도 예측 초록",
    pub_date=date(2021, 5, 1),
    url="https://openalex.org/W1",
    text_basis="abstract",
)
PAPER_CHUNKS = [
    Chunk(chunk_id=f"{PAPER.doc_id}#{i}", doc_id=PAPER.doc_id, ordinal=i, text=f"궤도 틀림 {i}")
    for i in range(3)
]
OLD = Document(
    doc_id="scienceon:old-2012",
    source="scienceon",
    doc_type="paper",
    title="궤도 검측 옛 논문",
    pub_date=date(2012, 1, 1),
)
OLD_CHUNK = Chunk(chunk_id=f"{OLD.doc_id}#0", doc_id=OLD.doc_id, ordinal=0, text="궤도 검측 " * 200)


def _app():
    app, a, _ = build()
    a.repo.seed([PAPER, OLD], [*PAPER_CHUNKS, OLD_CHUNK])
    return app


async def test_docs_are_grouped_and_carry_display_fields_only():
    async with client_for(_app()) as c:
        r = await c.get("/v1/search/docs", params={"q": "궤도", "limit": 10}, headers=AUTH)
    assert r.status_code == 200
    docs = r.json()["docs"]
    ids = [d["doc_id"] for d in docs]
    assert len(ids) == len(set(ids))  # 청크 3개 → 문서 한 줄
    paper = next(d for d in docs if d["doc_id"] == PAPER.doc_id)
    assert paper["title"] == "궤도 틀림 열화 예측"
    assert paper["source_label"] == "OpenAlex 논문"
    assert paper["year"] == 2021 and paper["url"] == "https://openalex.org/W1"
    assert paper["summary"].startswith("궤도 틀림") and paper["trust"] == "untrusted"
    old = next(d for d in docs if d["doc_id"] == OLD.doc_id)
    assert len(old["summary"]) <= 300 and old["summary"].endswith("…")
    internal = next(d for d in docs if d["doc_id"] == INTERNAL_DOC.doc_id)
    assert internal["url"] is None  # 사내 전용은 원문 링크 없음


async def test_source_and_year_filters_and_limit():
    async with client_for(_app()) as c:
        r = await c.get(
            "/v1/search/docs", params={"q": "궤도", "sources": "openalex,scienceon"}, headers=AUTH
        )
        assert {d["source"] for d in r.json()["docs"]} == {"openalex", "scienceon"}
        years = {"q": "궤도", "year_from": 2020, "year_to": 2026}
        r = await c.get("/v1/search/docs", params=years, headers=AUTH)
        # 연도 모르는 문서는 빠진다
        assert [d["doc_id"] for d in r.json()["docs"]] == [PAPER.doc_id]
        r = await c.get("/v1/search/docs", params={"q": "궤도", "limit": 1}, headers=AUTH)
        assert len(r.json()["docs"]) == 1
        bad = [
            {"q": "궤도", "sources": "nope"},
            {"q": "궤도", "year_from": 2025, "year_to": 2020},
            {"q": "궤도", "limit": 99},
            {"q": "   "},
        ]
        for params in bad:
            assert (
                await c.get("/v1/search/docs", params=params, headers=AUTH)
            ).status_code == 422, params


async def test_doc_id_query_returns_that_document():
    """근거 패널 [원본 보기] 는 /search?q=<문서 번호> 로 연다 — 그 문서 하나."""
    async with client_for(_app()) as c:
        r = await c.get("/v1/search/docs", params={"q": OLD.doc_id}, headers=AUTH)
    assert [d["doc_id"] for d in r.json()["docs"]] == [OLD.doc_id]


async def test_guest_never_sees_internal_documents_and_logged_out_gets_nothing():
    app = _app()
    async with client_for(app) as guest, client_for(app) as anon:
        await login(guest, kind="guest", id="team", password=GUEST[1])
        for params in (
            {"q": "궤도 틀림 사내 비공개", "limit": 30},
            {"q": INTERNAL_DOC.doc_id},
            {"q": "궤도", "sources": "alio"},
        ):
            r = await guest.get("/v1/search/docs", params=params)
            assert r.status_code == 200
            assert all(d["doc_id"] != INTERNAL_DOC.doc_id for d in r.json()["docs"]), params
            assert "사내 비공개" not in r.text
        r = await anon.get("/v1/search/docs", params={"q": "궤도"})
        assert r.status_code == 401 and "궤도" not in r.text
