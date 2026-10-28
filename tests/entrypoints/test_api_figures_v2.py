"""[G] REST 그림 v2 — 그림 목록의 기법 추천 결과·기법 목록, 추천 배지·항목 출처 필드,
추천 카드 동작(accept·dismiss·swap), [다시 추천](빈 결과도 사유), [다른 그림 추가] 기법."""

from __future__ import annotations

import json

import httpx
import pytest

from rra.application.services import ProposalAssistant, RunManager
from rra.application.usecases.figures import FigureConfig, MakeFigures
from rra.application.usecases.generate_proposal import GenerateProposal
from rra.application.usecases.precheck_overlap import PrecheckOverlap
from rra.composition import api_middlewares
from rra.domain.rules.lint import ChoiceSpec, LintRules
from rra.domain.rules.overlap import OwnUnit
from rra.entrypoints.api import create_app
from rra.entrypoints.api.app import SessionAuth
from rra.settings import Settings
from tests.entrypoints.test_api_figures import ANSWERS, AUTH, SLOTS, TOKEN
from tests.entrypoints.ui.fake_app import CHUNKS, DOCS, KEYS, TITLES
from tests.fakes import (
    FakeFigureRenderer,
    FakeImageGenerator,
    FakeLLM,
    FakePromptLibrary,
    FakeRenderer,
    FakeRunLog,
    FakeSlot,
    FakeTaskRunner,
    InMemoryRepository,
    InMemoryRunStore,
)
from tests.figure_v2_helpers import CATALOG, RoutingLLM, picks

PUGH = {
    "columns": ["현행 방식", "제안 방식"],
    "rows": [
        {"name": "구간별 진행 속도", "cells": ["0", "+"], "source": "s:method:0"},
        {"name": "궤도 틀림 반복", "cells": ["0", "+"], "source": "input:current_state"},
    ],
}
PMI = {
    "groups": [
        {
            "name": "Plus(장점)",
            "items": [{"text": "검측 이력", "source": "s:method:0", "rating": "상"}],
        },
        {
            "name": "Minus(단점)",
            "items": [{"text": "노반 침하", "source": "input:root_cause", "rating": "중"}],
        },
        {
            "name": "Interesting(흥미로운 점)",
            "items": [{"text": "열화 예측", "source": "input:goal", "rating": "중"}],
        },
    ]
}


def build(argon):
    repo = InMemoryRepository()
    repo.seed(DOCS, CHUNKS)
    rules = LintRules(
        template="test_v1",
        sections=KEYS,
        required_sections=["title", "task_type", "method", "utilization"],
        choices={
            "task_type": ChoiceSpec(options="task_types"),
            "utilization": ChoiceSpec(options="utilization", max=10),
            "strategy_alignment": ChoiceSpec(options="strategy_catalog", max=2),
        },
        titles=TITLES,
    )
    gen = GenerateProposal(FakeLLM(list(ANSWERS)), repo, FakePromptLibrary(), rules, KEYS)
    figures = MakeFigures(
        RoutingLLM(),
        FakePromptLibrary(),
        FakeFigureRenderer(),
        images=FakeImageGenerator(),
        argon=argon,
        argon_model="gemini-4-argon",
        config=FigureConfig(max_default=4),
        titles=TITLES,
        clock=lambda: "2026-10-28T10:00:00+00:00",
        catalog=CATALOG,
    )
    mgr = RunManager(
        gen,
        InMemoryRunStore(),
        FakeSlot(),
        FakeRunLog(),
        FakeTaskRunner(),
        clock=lambda: "2026-10-28T10:00:00+00:00",
        renderer=FakeRenderer(),
        figures=figures,
    )
    assistant = ProposalAssistant(
        PrecheckOverlap(repo, own=OwnUnit(org="korail", departments=frozenset({"철도연구원"}))),
        mgr,
        repo,
        clock=lambda: "2026-10-28T10:00:00+00:00",
        differentiate=None,
        recommend=None,
        recommend_auto=False,
    )
    from rra.adapters.security import SessionStore

    sessions = SessionStore()
    app = create_app(
        manager=mgr,
        precheck=assistant.precheck,
        repo=repo,
        user=assistant.user,
        middlewares=api_middlewares(Settings(_env_file=None), TOKEN, sessions=sessions),
        session_auth=SessionAuth(TOKEN, sessions),
        sse_poll_sec=0.01,
    )
    return app, mgr


@pytest.fixture
async def client():
    argon = RoutingLLM(picks=picks("pugh"), techniques={"pugh": PUGH, "pmi": PMI})
    app, mgr = build(argon)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    ) as c:
        c.mgr, c.argon = mgr, argon  # type: ignore[attr-defined]
        yield c


async def _run(client) -> str:
    r = await client.post("/v1/runs", json=SLOTS, headers=AUTH)
    assert r.status_code == 202, r.text
    rid = r.json()["run_id"]
    await client.mgr.wait("local", rid)
    return rid


async def test_figures_route_has_technique_outcome_catalog_and_badge_fields(client):
    rid = await _run(client)
    body = (await client.get(f"/v1/runs/{rid}/figures", headers=AUTH)).json()
    out = body["techniques"]
    assert out["status"] == "recommended" and out["status_label"] == "추천함"
    assert out["picks"] == [{"key": "pugh", "label": "퓨 매트릭스(Pugh)"}] and out["can_retry"]
    assert len(body["technique_catalog"]) == 20
    assert {"key", "label", "family_label", "summary", "fits"} <= set(body["technique_catalog"][0])
    fig = body["figures"][0]
    assert fig["kind"] == "technique" and fig["label"] == "퓨 매트릭스(Pugh)"
    assert fig["technique"] == "pugh" and fig["family_label"] == "비교·평가"
    assert fig["prelim_note"] == "제안 내용 기반 예비 평가"
    rec = fig["recommendation"]
    assert rec["status"] == "pending" and rec["status_label"] == "결정 전" and rec["reason"]
    prov = fig["provenance"]
    assert prov[0]["source_kind"] == "sentence" and prov[0]["section"] == "method"
    assert prov[0]["sentence_no"] == 1 and prov[1]["source_label"] == "제안 입력: 현재 상황·문제"
    draft = (await client.get(f"/v1/runs/{rid}/draft", headers=AUTH)).json()
    assert draft["figures"][0]["recommendation"]["status"] == "pending"


async def test_recommendation_actions_and_swap_over_rest(client):
    rid = await _run(client)
    fid = (await client.get(f"/v1/runs/{rid}/figures", headers=AUTH)).json()["figures"][0]["id"]
    r = await client.post(
        f"/v1/runs/{rid}/figures/{fid}", json={"action": "accept", "base_version": 1}, headers=AUTH
    )
    assert r.status_code == 200 and r.json()["version"] == 2
    assert r.json()["figures"][0]["recommendation"]["status_label"] == "넣기 확정"
    r = await client.post(f"/v1/runs/{rid}/figures/{fid}", json={"action": "dismiss"}, headers=AUTH)
    assert r.json()["figures"][0]["included"] is False
    r = await client.post(
        f"/v1/runs/{rid}/figures/{fid}", json={"action": "swap", "technique": "pmi"}, headers=AUTH
    )
    assert r.status_code == 200, r.text
    fig = r.json()["figures"][0]
    assert fig["technique"] == "pmi" and fig["included"] is True
    assert fig["recommendation"]["swapped_from_label"] == "퓨 매트릭스(Pugh)"
    bad = await client.post(
        f"/v1/runs/{rid}/figures/{fid}", json={"action": "swap", "technique": "lcc"}, headers=AUTH
    )
    assert bad.status_code == 409 and "해당 없음" in bad.json()["detail"]
    versions = (await client.get(f"/v1/runs/{rid}/versions", headers=AUTH)).json()
    assert len(versions["versions"]) == 4


async def test_retry_route_reports_empty_result_and_adds_technique(client):
    rid = await _run(client)
    client.argon.picks = {"picks": [], "none_reason": "비교할 대안이 본문에 없음"}
    r = await client.post(f"/v1/runs/{rid}/figures/techniques", json={}, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] is False and body["techniques"]["status"] == "none"
    assert body["techniques"]["message"] == "해당 없음 — 비교할 대안이 본문에 없음"
    listed = (await client.get(f"/v1/runs/{rid}/figures", headers=AUTH)).json()
    assert listed["techniques"]["status_label"] == "해당 없음"
    client.argon.picks = picks("pmi")
    r = await client.post(
        f"/v1/runs/{rid}/figures/techniques", json={"base_version": 1}, headers=AUTH
    )
    body = r.json()
    assert body["created"] is True and body["version"] == 2
    assert {f["technique"] for f in body["figures"]} == {"pugh", "pmi"}
    full = await client.post(f"/v1/runs/{rid}/figures/techniques", json={}, headers=AUTH)
    assert full.status_code == 409 and "이미 2장" in full.json()["detail"]
    # [다른 그림 추가] 기법 — 추천 배지 없음
    r = await client.post(
        f"/v1/runs/{rid}/figures",
        json={"kind": "technique", "section": "method", "technique": "pugh"},
        headers=AUTH,
    )
    assert r.status_code == 200, r.text
    added = [f for f in r.json()["figures"] if f["recommendation"] is None]
    assert added and added[0]["technique"] == "pugh"
    bad = await client.post(
        f"/v1/runs/{rid}/figures", json={"kind": "technique", "section": "method"}, headers=AUTH
    )
    assert bad.status_code == 409
    assert json.loads(bad.text)["detail"] == "분석 기법을 골라 주십시오."
