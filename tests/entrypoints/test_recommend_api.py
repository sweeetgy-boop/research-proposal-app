"""REST — 차별화 과제 추천.

precheck 자동 첨부, 다시 받기, 적용 미리보기, run 복사·manifest 기록 (가짜 유스케이스).
"""

from __future__ import annotations

import httpx

from rra.domain.models import ProjectRecommendation, RecommendationResult
from tests.entrypoints.test_api import AUTH, SLOTS, build
from tests.entrypoints.ui.fake_app import make_assistant


class FakeRecommend:
    def __init__(self, recs=None, reason=None):
        self.calls = []
        self.recs = recs
        self.reason = reason

    async def __call__(self, req, alerts):
        self.calls.append((req, alerts))
        recs = (
            [
                ProjectRecommendation(
                    title="가제",
                    summary="요약임",
                    differentiation="차별점임",
                    reasons=["alio:1 과 대상이 다름"],
                    risks="확인할 점",
                    compared_with=["alio:1"],
                    evidence=["alio:1"],
                )
            ]
            if self.recs is None
            else self.recs
        )
        return RecommendationResult(
            recommendations=recs,
            no_recommendation_reason=self.reason if not recs else None,
            provider="gemini",
            model="argon",
            public_doc_ids=["alio:1"],
            calls=1,
        )


def client_for(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    )


async def test_precheck_attaches_recommendations_with_session_id_when_auto():
    fake = FakeRecommend()
    app, _ = build(make_assistant(), recommend=fake)
    async with client_for(app) as c:
        r = await c.post("/v1/precheck", json=SLOTS, headers=AUTH)
        body = r.json()
        rec = body["recommendations"]
        assert len(rec["id"]) == 24 and rec["recommendations"][0]["index"] == 0
        assert rec["recommendations"][0]["title"] == "가제"
        assert rec["transfer"]["public_doc_ids"] == ["alio:1"] and rec["provider"] == "gemini"
        assert fake.calls and fake.calls[0][0].goal == SLOTS["goal"]
    app, _ = build(make_assistant(), recommend=fake, recommend_auto=False)
    async with client_for(app) as c:
        r = await c.post("/v1/precheck", json=SLOTS, headers=AUTH)
        assert "recommendations" not in r.json()  # recommend.auto=false → 요청 시만


async def test_recommend_route_apply_preview_and_run_copies_result_into_manifest():
    fake = FakeRecommend()
    app, assistant = build(make_assistant(), recommend=fake, recommend_auto=False)
    async with client_for(app) as c:
        r = await c.post("/v1/precheck/recommendations", json=SLOTS, headers=AUTH)
        assert r.status_code == 200, r.text
        rec_id = r.json()["recommendations"]["id"]
        # 적용 미리보기 — 저장하지 않고 바뀐 칸만
        r = await c.post(
            f"/v1/precheck/recommendations/{rec_id}/apply", json={"index": 0}, headers=AUTH
        )
        assert r.status_code == 200, r.text
        pv = r.json()
        assert pv["changed"] == ["title_hint", "goal", "differentiation"]
        assert pv["after"]["title_hint"] == "가제" and pv["after"]["goal"].startswith(SLOTS["goal"])
        assert pv["request"]["current_state"] == SLOTS["current_state"]
        bad = await c.post(
            f"/v1/precheck/recommendations/{rec_id}/apply", json={"index": 3}, headers=AUTH
        )
        assert bad.status_code == 422
        missing = await c.post(
            "/v1/precheck/recommendations/0123456789abcdef/apply", json={"index": 0}, headers=AUTH
        )
        assert missing.status_code == 404
        # 확정 입력으로 생성 — 세션 id 로 run 에 복사, manifest 에 전송 기록 + chosen
        payload = {**pv["request"], "recommendation_id": rec_id, "recommendation_index": 0}
        r = await c.post("/v1/runs", json=payload, headers=AUTH)
        assert r.status_code == 202, r.text
        run_id = r.json()["run_id"]
        await assistant.manager.wait(assistant.user, run_id)
        saved = assistant.manager.store.load_recommendations(assistant.user, run_id)
        assert saved["recommendations"][0]["title"] == "가제"
        manifests = [m for rid, m in assistant.manager.run_log.records if rid == run_id]
        rec_m = manifests[-1]["recommendations"]
        assert rec_m["chosen"] == 0 and rec_m["recommendations"] == 1
        assert rec_m["public_doc_ids"] == ["alio:1"] and "title" not in rec_m
        from rra.adapters.logging import check_manifest

        check_manifest(manifests[-1])
        unknown = {**SLOTS, "recommendation_id": "0123456789abcdef"}
        assert (await c.post("/v1/runs", json=unknown, headers=AUTH)).status_code == 404
        over = {**SLOTS, "recommendation_id": rec_id, "recommendation_index": 4}
        assert (await c.post("/v1/runs", json=over, headers=AUTH)).status_code == 422


async def test_zero_recommendations_return_reason_and_route_is_503_without_llm():
    fake = FakeRecommend(recs=[], reason="아이디어가 이미 충분히 다름")
    app, _ = build(make_assistant(), recommend=fake)
    async with client_for(app) as c:
        r = await c.post("/v1/precheck", json=SLOTS, headers=AUTH)
        rec = r.json()["recommendations"]
        assert rec["recommendations"] == [] and "충분히 다름" in rec["no_recommendation_reason"]
    app, _ = build(make_assistant())
    async with client_for(app) as c:
        r = await c.post("/v1/precheck/recommendations", json=SLOTS, headers=AUTH)
        assert r.status_code == 503 and "LLM" in r.json()["detail"]
        r = await c.post("/v1/precheck", json=SLOTS, headers=AUTH)
        assert "recommendations" not in r.json()
