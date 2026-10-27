"""REST U1~U8 경로 — 인증 미들웨어 뒤에서, 가짜 유스케이스·FakeLLM 으로."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from rra.composition import api_middlewares
from rra.domain.models import PriorWorkBrief, StructuredIdea
from rra.domain.models.comparison import ComparisonColumn, ComparisonTable
from rra.entrypoints.api import create_app
from rra.settings import Settings
from tests.entrypoints.test_api import AUTH, SLOTS, TOKEN
from tests.entrypoints.ui.fake_app import make_assistant


class FakeStructure:
    async def __call__(self, text, *, title=""):
        return StructuredIdea(
            fields={"current_state": text[:20], "root_cause": "", "limitation": "", "goal": ""},
            questions=[],
            provider="mlx",
        )


class FakeCompare:
    async def __call__(self, req, alerts):
        return ComparisonTable(
            proposal=ComparisonColumn(title=req.title_hint, cells={"objective": req.goal}),
            projects=[
                ComparisonColumn(
                    doc_id=a.doc_id, title=a.title, cells={"objective": "정보 없음(제목 기준)"}
                )
                for a in alerts
            ],
        )


class FakeBrief:
    async def __call__(self, req):
        return PriorWorkBrief(items=[], years={}, keywords=["궤도"], provider="gemini", calls=1)


def build(**kw):
    from rra.adapters.security import SessionStore
    from rra.entrypoints.api.app import SessionAuth

    a = make_assistant(blocking=kw.pop("blocking", False))
    settings = Settings(_env_file=None)
    sessions = SessionStore()
    app = create_app(
        manager=a.manager,
        precheck=a.precheck,
        differentiate=None,
        recommend=None,
        repo=a.repo,
        user=a.user,
        middlewares=api_middlewares(settings, TOKEN, sessions=sessions),
        session_auth=SessionAuth(TOKEN, sessions),
        sse_poll_sec=0.01,
        **kw,
    )
    return app, a


@pytest.fixture
async def client():
    app, a = build(
        structure=FakeStructure(), compare=FakeCompare(), brief=FakeBrief(), blocking=True
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        c.assistant = a  # type: ignore[attr-defined]
        yield c


async def _drafted(client):
    r = await client.post(
        "/v1/runs", json={**SLOTS, "priority_evidence": ["openalex:W1", "zzz"]}, headers=AUTH
    )
    assert r.status_code == 202
    rid = r.json()["run_id"]
    mgr = client.assistant.manager
    await mgr.wait("local", rid)
    return rid, mgr


async def test_precheck_side_routes_structure_merge_comparison_brief(client):
    r = await client.post("/v1/ideas/structure", json={"text": "궤도 틀림이 잦음"}, headers=AUTH)
    assert r.status_code == 200 and r.json()["fields"]["current_state"] == "궤도 틀림이 잦음"
    assert r.json()["labels"]["goal"] == "해결 목표" and "notice" in r.json()
    r = await client.post(
        "/v1/ideas/structure/merge",
        json={"fields": {"current_state": "궤도 틀림이 잦음"}, "answers": {"goal": "열화 예측"}},
        headers=AUTH,
    )
    assert r.status_code == 200 and r.json()["fields"]["goal"] == "열화 예측"
    assert [q["field"] for q in r.json()["questions"]] == ["root_cause", "limitation"]
    r = await client.post("/v1/precheck/comparison", json=SLOTS, headers=AUTH)
    assert r.status_code == 200 and r.json()["blocking"] is True
    assert r.json()["comparison"]["projects"][0]["doc_id"] == "alio:1"
    assert r.json()["comparison"]["aspects"][0]["label"] == "연구목표"
    r = await client.post("/v1/precheck/brief", json=SLOTS, headers=AUTH)
    assert r.status_code == 200 and r.json()["keywords"] == ["궤도"] and "gap_label" in r.json()
    r = await client.post("/v1/ideas/structure", json={"text": ""}, headers=AUTH)
    assert r.status_code == 422
    assert (await client.post("/v1/ideas/structure", json={"text": "x"})).status_code == 401


async def test_missing_usecases_are_503():
    app, _ = build()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        for path in ("/v1/ideas/structure", "/v1/precheck/comparison", "/v1/precheck/brief"):
            body = {"text": "x"} if "ideas" in path else SLOTS
            assert (await c.post(path, json=body, headers=AUTH)).status_code == 503


async def test_run_routes_evidence_decisions_rewrite_questions_submit_check_usage_feedback(client):
    rid, mgr = await _drafted(client)
    assert mgr.store.load_snapshot("local", rid).priority_ids == ["openalex:W1"]
    r = await client.get(f"/v1/runs/{rid}/sentences/s:method:1/evidence", headers=AUTH)
    assert r.status_code == 200
    item = r.json()["evidence"][0]
    assert item["evidence_id"] == "openalex:W1#0" and item["title"] == "Track geometry monitoring"
    assert item["basis_label"] == "원문" and item["trust"] == "untrusted"
    assert (
        await client.get(f"/v1/runs/{rid}/sentences/s:method:9/evidence", headers=AUTH)
    ).status_code == 404

    r = await client.post(
        f"/v1/runs/{rid}/evidence-decisions",
        json={
            "decisions": [
                {"sentence_id": "s:method:1", "evidence_id": "openalex:W1#0", "action": "approve"}
            ],
            "base_version": 1,
        },
        headers=AUTH,
    )
    assert r.status_code == 200 and r.json()["version"] == 2 and r.json()["status"] == "editing"
    assert r.json()["evidence_decisions"] == [
        {"sentence_id": "s:method:1", "evidence_id": "openalex:W1#0", "action": "approve"}
    ]
    r = await client.post(
        f"/v1/runs/{rid}/evidence-decisions",
        json={
            "decisions": [
                {"sentence_id": "s:method:1", "evidence_id": "openalex:W1#0", "action": "exclude"}
            ],
            "base_version": 1,
        },
        headers=AUTH,
    )
    assert r.status_code == 409  # 기준 버전 불일치
    r = await client.post(
        f"/v1/runs/{rid}/evidence-decisions", json={"decisions": []}, headers=AUTH
    )
    assert r.status_code == 409  # 반영할 판단 없음
    r = await client.post(
        f"/v1/runs/{rid}/evidence-decisions", json={"decisions": "x"}, headers=AUTH
    )
    assert r.status_code == 422

    r = await client.get(f"/v1/runs/{rid}/sections/method/questions", headers=AUTH)
    assert r.status_code == 200 and r.json()["questions"] == [] and r.json()["answers"] == {}
    r = await client.post(
        f"/v1/runs/{rid}/sections/method/answers",
        json={"answers": {"산출물": "보고서"}},
        headers=AUTH,
    )
    assert r.status_code == 200 and r.json()["answers"] == {"산출물": "보고서"}
    assert (
        await client.get(f"/v1/runs/{rid}/sections/nope/questions", headers=AUTH)
    ).status_code == 404

    mgr.generate.llm.responses.append(
        '[{"text": "다시 쓴 문장임.", "evidence": ["openalex:W1#0"]}]'
    )
    r = await client.post(f"/v1/runs/{rid}/sections/method/rewrite", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["candidate"][0]["text"] == "다시 쓴 문장임." and "notice" in r.json()
    assert "산출물" in mgr.generate.llm.calls[-1]
    r = await client.post(
        f"/v1/runs/{rid}/sections/method/rewrite/apply", json={"chosen": [0]}, headers=AUTH
    )
    assert r.status_code == 200 and r.json()["version"] == 3 and r.json()["note"] == "AI 다시 쓰기"
    assert (
        await client.post(f"/v1/runs/{rid}/sections/method/rewrite/apply", json={}, headers=AUTH)
    ).status_code == 409

    r = await client.get(f"/v1/runs/{rid}/submit-check", headers=AUTH)
    assert r.status_code == 200
    keys = [i["key"] for i in r.json()["items"]]
    assert "strategy_source" in keys and "review_state" in keys
    choices = next(i for i in r.json()["items"] if i["key"] == "choices_confirmed")
    assert choices["ok"] is False and choices["target"] == "section:task_type"
    assert choices["target_label"] == "1-다 과제유형"

    r = await client.get(f"/v1/runs/{rid}/usage", headers=AUTH)
    assert r.status_code == 200 and r.json()["usage"]["rewrites"] == 1
    assert (
        r.json()["usage"]["evidence"]["ratios"]["approve"] == 0.0
    )  # 다시 쓴 문장은 판단이 떨어진다
    r = await client.post(f"/v1/runs/{rid}/feedback", json={"score": 5}, headers=AUTH)
    assert r.status_code == 409  # 마무리 전
    fin = await client.post(
        f"/v1/runs/{rid}/finalize",
        json={"task_type": "applied", "utilization": ["software"]},
        headers=AUTH,
    )
    assert fin.status_code == 200
    r = await client.post(
        f"/v1/runs/{rid}/feedback", json={"score": 5, "comment": "좋음"}, headers=AUTH
    )
    assert r.status_code == 200 and r.json()["usage"]["satisfaction"]["score"] == 5
    assert r.json()["usage"]["hwpx_success"] is True
    r = await client.post(
        f"/v1/runs/{rid}/feedback", json={"score": 5, "comment": "a@b.c"}, headers=AUTH
    )
    assert r.status_code == 422
    r = await client.post(f"/v1/runs/{rid}/feedback", json={"score": 9}, headers=AUTH)
    assert r.status_code == 422


async def test_feature_disabled_is_503(client):
    from rra.domain.models import UsabilityConfig

    rid, mgr = await _drafted(client)
    mgr.usability = UsabilityConfig(submit_check=False)
    assert (await client.get(f"/v1/runs/{rid}/submit-check", headers=AUTH)).status_code == 503


def test_openapi_lists_the_new_paths():
    app, _ = build()
    paths = set(app.openapi()["paths"])
    for p in (
        "/v1/ideas/structure",
        "/v1/ideas/structure/merge",
        "/v1/precheck/comparison",
        "/v1/precheck/brief",
        "/v1/runs/{run_id}/sentences/{sid}/evidence",
        "/v1/runs/{run_id}/evidence-decisions",
        "/v1/runs/{run_id}/sections/{key}/rewrite",
        "/v1/runs/{run_id}/sections/{key}/rewrite/apply",
        "/v1/runs/{run_id}/sections/{key}/questions",
        "/v1/runs/{run_id}/sections/{key}/answers",
        "/v1/runs/{run_id}/submit-check",
        "/v1/runs/{run_id}/usage",
        "/v1/runs/{run_id}/feedback",
    ):
        assert p in paths, p
    assert asyncio.iscoroutinefunction(FakeBrief.__call__) and json.dumps(sorted(paths))
