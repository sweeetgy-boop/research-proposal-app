"""[G] REST — 초안 응답의 figures, 그림 파일 경로(소유자·variant·version), 카드 동작(새 버전·409),
추가. 가짜 LLM·가짜 이미지 생성기, 네트워크 없음."""

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

TOKEN = "api-test-token"  # noqa: S105 — 테스트용
AUTH = {"X-RRA-Token": TOKEN}
SLOTS = {
    "current_state": "궤도 틀림 반복",
    "root_cause": "노반 침하",
    "limitation": "임계치만 봄",
    "goal": "열화 예측",
}
METHOD = "검측 이력을 분석해 구간별 진행 속도를 추정함."
ANSWERS = [
    json.dumps([{"text": "궤도 틀림 열화 예측 연구", "evidence": []}], ensure_ascii=False),
    json.dumps({"choices": ["applied"], "sentences": [{"text": "응용 사유", "evidence": []}]}),
    json.dumps([{"text": METHOD, "evidence": []}], ensure_ascii=False),
    json.dumps({"choices": ["software"], "sentences": [{"text": "프로그램 제공", "evidence": []}]}),
    json.dumps({"choices": [], "sentences": []}),
]
PROCESS = {
    "stages": [
        {"name": "검측 이력 분석", "outputs": ["구간별 진행 속도"]},
        {"name": "진행 속도 추정"},
        {"name": "열화 예측"},
    ]
}


def build():
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
    images = FakeImageGenerator()
    figures = MakeFigures(
        FakeLLM([json.dumps(PROCESS, ensure_ascii=False)] * 4),
        FakePromptLibrary(),
        FakeFigureRenderer(),
        images=images,
        config=FigureConfig(max_default=3, auto_kinds=("process",)),  # 예전 세트로 동작 시험
        titles=TITLES,
        clock=lambda: "2026-10-28T10:00:00+00:00",
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
    settings = Settings(_env_file=None)
    from rra.adapters.security import SessionStore

    sessions = SessionStore()
    app = create_app(
        manager=mgr,
        precheck=assistant.precheck,
        repo=repo,
        user=assistant.user,
        middlewares=api_middlewares(settings, TOKEN, sessions=sessions),
        session_auth=SessionAuth(TOKEN, sessions),
        sse_poll_sec=0.01,
    )
    return app, mgr, images


@pytest.fixture
async def client():
    app, mgr, images = build()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    ) as c:
        c.mgr = mgr  # type: ignore[attr-defined]
        c.images = images  # type: ignore[attr-defined]
        yield c


async def _run(client) -> str:
    r = await client.post("/v1/runs", json=SLOTS, headers=AUTH)
    assert r.status_code == 202, r.text
    rid = r.json()["run_id"]
    await client.mgr.wait("local", rid)
    return rid


async def test_draft_lists_figures_and_image_routes_serve_files(client):
    rid = await _run(client)
    d = (await client.get(f"/v1/runs/{rid}/draft", headers=AUTH)).json()
    figs = d["figures"]
    assert [f["kind"] for f in figs] == ["process"] and figs[0]["section"] == "method"
    fig = figs[0]
    assert (
        fig["renderer_label"] == "Nano Banana Pro" and fig["confirmed"] is False and fig["included"]
    )
    assert fig["texts"][0]["path"] == "stages.0.name" and fig["notice"].startswith("AI 가 그린")
    assert fig["spec_model"] == "local" and fig["last_change"] is None
    assert fig["image_url"] == f"/v1/runs/{rid}/figures/{fig['id']}/image"
    img = await client.get(fig["image_url"], headers=AUTH)
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert img.content.startswith(b"NB:") and "nosniff" in img.headers["x-content-type-options"]
    base = await client.get(fig["baseline_url"], headers=AUTH)
    assert base.status_code == 200 and base.headers["content-type"] == "image/png"
    assert (
        await client.get(f"/v1/runs/{rid}/figures/f:none:1/image", headers=AUTH)
    ).status_code == 404
    assert (await client.get(fig["image_url"])).status_code == 401
    listed = (await client.get(f"/v1/runs/{rid}/figures", headers=AUTH)).json()
    assert listed["version"] == 1 and listed["figures"][0]["id"] == fig["id"]


async def test_figure_actions_create_versions_and_conflict_is_409(client):
    rid = await _run(client)
    fid = (await client.get(f"/v1/runs/{rid}/draft", headers=AUTH)).json()["figures"][0]["id"]
    r = await client.post(
        f"/v1/runs/{rid}/figures/{fid}",
        json={"action": "texts", "texts": {"stages.0.name": "검측 자료 분석"}, "base_version": 1},
        headers=AUTH,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version"] == 2 and body["figures"][0]["texts"][0]["value"] == "검측 자료 분석"
    assert body["figures"][0]["confirmed"] is False and body["figures"][0]["calls"] == 2
    conflict = await client.post(
        f"/v1/runs/{rid}/figures/{fid}", json={"action": "confirm", "base_version": 1}, headers=AUTH
    )
    assert conflict.status_code == 409 and "v1" in conflict.json()["detail"]
    r = await client.post(f"/v1/runs/{rid}/figures/{fid}", json={"action": "confirm"}, headers=AUTH)
    assert r.json()["version"] == 3 and r.json()["figures"][0]["confirmed"] is True
    changed = json.loads(json.dumps(PROCESS, ensure_ascii=False))
    changed["stages"][0]["name"] = "검측 자료 분석"  # v2 글자 고치기 값 그대로 (현재 명세)
    changed["stages"][2]["name"] = "구간별 열화 예측"
    client.mgr.figures.llm.responses = [
        json.dumps({"spec": changed, "style": "화살표를 진하게", "summary": []}, ensure_ascii=False)
    ]
    r = await client.post(
        f"/v1/runs/{rid}/figures/{fid}",
        json={"action": "words", "request": "3단계를 '구간별 열화 예측'으로, 화살표를 진하게"},
        headers=AUTH,
    )
    assert r.status_code == 200, r.text
    fig = r.json()["figures"][0]
    assert fig["edit_requests"] == 1 and fig["confirmed"] is False
    assert fig["last_change"] == {
        "kind": "content",
        "summary": ["단계 3 '열화 예측' → '구간별 열화 예측'", "모양: 화살표를 진하게"],
        "style": "화살표를 진하게",
        "model": "local",
        "at": "2026-10-28T10:00:00+00:00",
    }
    assert {c["kind"] for c in client.images.calls} == {"generate"}  # 편집 호출 없음
    assert "모양 요청(제안자): 화살표를 진하게" in client.images.calls[-1]["prompt"]
    client.mgr.figures.llm.responses = ["[]", "[]"]  # 읽을 수 없는 답 → 409 사유, 버전 없음
    r = await client.post(
        f"/v1/runs/{rid}/figures/{fid}", json={"action": "words", "request": "x"}, headers=AUTH
    )
    assert r.status_code == 409 and "json" in r.json()["detail"]
    r = await client.post(f"/v1/runs/{rid}/figures/{fid}", json={"action": "words"}, headers=AUTH)
    assert r.status_code == 409
    r = await client.post(f"/v1/runs/{rid}/figures/{fid}", json={"action": "fly"}, headers=AUTH)
    assert r.status_code == 422
    r = await client.post(f"/v1/runs/{rid}/figures/{fid}", json={"action": "exclude"}, headers=AUTH)
    assert r.json()["figures"][0]["included"] is False
    diff = (await client.get(f"/v1/runs/{rid}/versions/diff?from=1&to=5", headers=AUTH)).json()
    assert r.json()["figures"][0]["last_change"]["kind"] == "content"  # 버전이 바뀌어도 이어진다
    changes = {c["change"] for c in diff["figures_changed"]}
    assert {"texts", "excluded"} <= changes
    versions = (await client.get(f"/v1/runs/{rid}/versions", headers=AUTH)).json()["versions"]
    assert all(v["figures"] == 1 for v in versions)
    old = await client.get(f"/v1/runs/{rid}/figures/{fid}/image?version=1", headers=AUTH)
    assert old.status_code == 200
    check = (await client.get(f"/v1/runs/{rid}/submit-check", headers=AUTH)).json()
    keys = {i["key"]: i for i in check["items"]}
    assert keys["figures_unconfirmed"]["ok"] is True  # 뺀 그림은 확인 대상이 아니다


async def test_add_figure_route(client):
    rid = await _run(client)
    r = await client.post(
        f"/v1/runs/{rid}/figures", json={"kind": "process", "section": "method"}, headers=AUTH
    )
    assert r.status_code == 200, r.text
    ids = [f["id"] for f in r.json()["figures"]]
    assert ids == ["f:method:1", "f:method:2"] and r.json()["note"] == "그림 추가"
    bad = await client.post(
        f"/v1/runs/{rid}/figures", json={"kind": "poster", "section": "method"}, headers=AUTH
    )
    assert bad.status_code == 422
