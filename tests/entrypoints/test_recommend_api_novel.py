"""REST — 새 과제 추천 갈래 (ADR 0057): novel 세션은 [더 만들기]·적용 미리보기가 없고(409),
새로움 확인에서 새로 걸린 행(differentiate 로 되돌림)은 응답 최상위 alerts 에 더해진다."""

from __future__ import annotations

from rra.domain.models import OverlapAlert, RecommendationResult
from rra.domain.models.novel import (
    Barrier,
    BarrierBasis,
    NovelRecommendation,
    NovelTitle,
    NoveltyCoverage,
)
from tests.entrypoints.test_api import AUTH, SLOTS, build
from tests.entrypoints.test_recommend_api import FakeRecommend, client_for
from tests.entrypoints.ui.fake_app import make_assistant

NEW_ROW = OverlapAlert(
    doc_id="ntis:new1",
    title="넓은 검색에서 새로 찾은 과제",
    tier="national_rnd",
    similarity=0.9,
    blocking=False,
)


class FakeNovel:
    async def __call__(self, req, alerts, **kw):
        return RecommendationResult(
            mode="novel",
            coverage=NoveltyCoverage(searched=["own"], searched_labels=["사내 과제"]),
            novel=[
                NovelRecommendation(
                    approach="기존 감시 장비 활용",
                    summary="요약임",
                    maturity="실증 필요",
                    barriers=[
                        Barrier(
                            type="비용",
                            statement="설치비 부담",
                            basis=BarrierBasis(level="추정"),
                            check="역별 설치비 조사",
                        )
                    ],
                    titles=[NovelTitle(title="가제", resolves=[0], reason="비용 장벽 해소")],
                )
            ],
            provider="gemini",
            calls=1,
        )


class FakeReverted(FakeRecommend):
    async def __call__(self, req, alerts, **kw):
        out = await super().__call__(req, alerts, **kw)
        return out.model_copy(update={"novelty_reverted": True, "novelty_alerts": [NEW_ROW]})


async def test_novel_session_has_no_more_and_no_apply():
    app, _ = build(make_assistant(), recommend=FakeNovel(), recommend_auto=False)
    async with client_for(app) as c:
        r = await c.post("/v1/precheck/recommendations", json=SLOTS, headers=AUTH)
        assert r.status_code == 200, r.text
        rec = r.json()["recommendations"]
        assert "_novelty_rows" not in rec
        rec_id = rec["id"]
        r = await c.post(
            "/v1/precheck/recommendations/more",
            json={"rec_id": rec_id, "request": SLOTS},
            headers=AUTH,
        )
        assert r.status_code == 409 and "다시 만들기" in r.text
        r = await c.post(
            f"/v1/precheck/recommendations/{rec_id}/apply", json={"index": 0}, headers=AUTH
        )
        assert r.status_code == 409 and "과제명으로 진행" in r.text


async def test_reverted_rows_join_top_level_alerts():
    app, _ = build(make_assistant(), recommend=FakeReverted(), recommend_auto=False)
    async with client_for(app) as c:
        r = await c.post("/v1/precheck/recommendations", json=SLOTS, headers=AUTH)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "ntis:new1" in [a["doc_id"] for a in body["alerts"]]
        assert "_novelty_rows" not in body["recommendations"]
    # stage=full 자동 첨부도 같은 규칙
    app, _ = build(make_assistant(), recommend=FakeReverted())
    async with client_for(app) as c:
        r = await c.post("/v1/precheck", json=SLOTS, headers=AUTH)
        body = r.json()
        assert "ntis:new1" in [a["doc_id"] for a in body["alerts"]]
        assert "_novelty_rows" not in body["recommendations"]
