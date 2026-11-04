"""② v3 REST — 가짜 모드 (2026-10-28 밤 레인 A, ADR 0039).

표 먼저(stage=rule, judgment pending) → /judgment(판정 칸·기본 선택) → /recommendations(근거
제목·자료원,
카드 겹침 재판정) → /recommendations/more(이미 보인 안과 다른 안, 번호 이어짐). 겹친 카드 다시
받기는
가짜 저장소가 reranker 점수를 내지 않아 유스케이스
테스트(tests/application/test_precheck_v3.py)에서 본다.
"""

from __future__ import annotations

import re

import httpx

from tests.entrypoints.test_precheck_flow_api import AUTH, IDEA, parts  # noqa: F401 — 픽스처

INTERNAL = re.compile(r"\b(own|alio|ntis|scienceon|openalex|korail_web|g2b):[\w-]+")


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    )


async def test_table_first_then_judgment_then_cards_and_more(parts):  # noqa: F811
    async with _client(parts["app"]) as c:
        fast = (await c.post("/v1/precheck?stage=rule", json=IDEA, headers=AUTH)).json()
        assert fast["judgment"]["status"] == "pending" and fast["judgment"]["message"]
        assert "recommendations" not in fast  # 과제안은 따로
        assert {a["level_basis"] for a in fast["alerts"]} == {"rule"}
        assert all(a["level_basis_label"] == "규칙 기준" for a in fast["alerts"])
        assert all(a["source_label"] for a in fast["alerts"])

        judged = (await c.post("/v1/precheck/judgment", json=IDEA, headers=AUTH)).json()
        assert judged["judgment"]["status"] == "ai"
        first, *rest = judged["alerts"]
        assert first["judgment"] == "same" and first["level"] == "blocking"
        assert first["level_label"] == "차단"
        assert all(a["level_label"] == "관련 낮음" for a in rest)  # 가짜: 나머지는 different
        # 기본 선택 (ADR 0054): '같다' → [유사함], '다르다' → [관련 없음]
        defaults = {d["doc_id"]: d["choice"] for d in judged["default_choices"]}
        assert defaults == {
            first["doc_id"]: "similar",
            **{a["doc_id"]: "unrelated" for a in rest},
        }
        assert (
            judged["similar_count"] == 1 and judged["blocking"] is True
        )  # 미리 고른 [유사함] 은 차단 유지

        rec = (await c.post("/v1/precheck/recommendations", json=IDEA, headers=AUTH)).json()
        cards = rec["recommendations"]
        assert len(cards["recommendations"]) == 2 and cards["overlap_checked"] is True
        refs = cards["recommendations"][0]["refs"]
        assert refs and refs[0]["title"] and refs[0]["source_label"]
        assert not INTERNAL.search(refs[0]["title"] + refs[0]["source_label"])

        more = (
            await c.post(
                "/v1/precheck/recommendations/more",
                json={"request": IDEA, "rec_id": cards["id"]},
                headers=AUTH,
            )
        ).json()["recommendations"]
        assert more["id"] == cards["id"] and more["added"] == 2
        titles = [r["title"] for r in more["recommendations"]]
        assert len(titles) == 4 and len(set(titles)) == 4  # 이미 보인 안과 겹치지 않는다
        assert [r["index"] for r in more["recommendations"]] == [0, 1, 2, 3]
        assert [r["added"] for r in more["recommendations"]] == [False, False, True, True]
        # 보탠 안도 apply 미리보기로 고를 수 있다 (번호 이어짐)
        ok = await c.post(
            f"/v1/precheck/recommendations/{cards['id']}/apply", json={"index": 3}, headers=AUTH
        )
        assert ok.status_code == 200
        missing = await c.post(
            "/v1/precheck/recommendations/more",
            json={"request": IDEA, "rec_id": "nope"},
            headers=AUTH,
        )
        assert missing.status_code == 404


async def test_full_stage_still_works_for_mcp_and_run_screen(parts):  # noqa: F811
    async with _client(parts["app"]) as c:
        full = (await c.post("/v1/precheck", json=IDEA, headers=AUTH)).json()
    assert full["judgment"]["status"] == "ai" and full["recommendations"]["recommendations"]
