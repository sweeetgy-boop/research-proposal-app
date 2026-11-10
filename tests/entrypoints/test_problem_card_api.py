"""REST — 문제 정의 카드 (`POST /v1/ideas/diagnose`·`/diagnose/edit`, ADR 0065 계약 3절).

라우트는 `problem_card_routes.register` 로 시험 앱에 붙인다(app.py 연결은 통합 때 — PR 설명).
유스케이스는 조립(`build_problem_diagnosis`·`build_card_editor`)이 가짜 모드로 만든다 —
설정 사본에서만 `enabled: true`(저장소의 config/problem_card.yaml 은 false 그대로). 네트워크·모델 없음.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from rra import composition
from rra.adapters.fake.llm import ScriptedComposeLLM
from rra.domain.models import Principal
from rra.domain.rules import auth_policy
from rra.entrypoints.api.problem_card_routes import register
from rra.settings import Settings
from tests.entrypoints.test_api import AUTH, build
from tests.entrypoints.test_recommend_api import client_for
from tests.entrypoints.ui.fake_app import make_assistant
from tests.fakes import InMemoryRepository

IDEA = {
    "title_hint": "철도역사 비둘기 침입 방지",
    "current_state": "역사 승강장 지붕에 비둘기가 드나들어 배설물 민원이 반복됨",
    "root_cause": "출입구가 열려 있어 비둘기 침입 경로가 막히지 않음",
    "limitation": "그물 설치는 미관을 해치고 유지관리가 어려움",
    "goal": "역사 구조에 맞는 비둘기 침입 방지 방법을 마련함",
}
STAFF = Principal(kind="staff", id="staff:aaaaaaaaaaaa")
GUEST = Principal(kind="guest", id="guest:demo")


def settings_for(tmp_path: Path, *, enabled: bool) -> Settings:
    cfg = tmp_path / "config"
    shutil.copytree(Path("config"), cfg, ignore=shutil.ignore_patterns("*.hwpx"))
    card = yaml.safe_load((cfg / "problem_card.yaml").read_text(encoding="utf-8"))
    card["enabled"] = enabled
    (cfg / "problem_card.yaml").write_text(yaml.safe_dump(card, allow_unicode=True), "utf-8")
    return Settings(_env_file=None, fake_llm=True, config_dir=cfg, data_dir=tmp_path / "data")


def app_for(tmp_path: Path, *, enabled: bool = True, who=None, wired: bool = True):
    app, _ = build(make_assistant(), recommend_auto=False)
    settings = settings_for(tmp_path, enabled=enabled)
    parts: dict = {"diagnosis": None, "editor": None, "edit_log": None, "choice_log": None}
    if wired:
        repo, llm = InMemoryRepository(), ScriptedComposeLLM()
        parts["edit_log"] = composition.build_card_edit_log(settings)
        parts["choice_log"] = composition.build_choice_log(settings)
        parts["diagnosis"] = composition.build_problem_diagnosis(
            settings, repo=repo, llm=llm, edit_log=parts["edit_log"]
        )
        parts["editor"] = composition.build_card_editor(
            settings,
            repo=repo,
            llm=llm,
            edit_log=parts["edit_log"],
            choice_log=parts["choice_log"],
        )
    register(
        app,
        api_version="v1",
        diagnosis=parts["diagnosis"],
        editor=parts["editor"],
        who=who or (lambda request: auth_policy.admin_principal()),
        clean=lambda s: s,
    )
    return app, parts


async def test_diagnose_off_returns_null_card_not_error(tmp_path):
    for kw in ({"enabled": False}, {"wired": False}):
        app, _ = app_for(tmp_path / str(len(kw) + int("wired" in kw)), **kw)
        async with client_for(app) as c:
            r = await c.post("/v1/ideas/diagnose", json=IDEA, headers=AUTH)
        body = r.json()
        assert r.status_code == 200
        assert (body["status"], body["card"], body["lines"]) == ("off", None, None)
        assert body["signal_labels"] == [] and body["reason"] is None


async def test_diagnose_ok_returns_card_lines_and_labels(tmp_path):
    app, _ = app_for(tmp_path)
    async with client_for(app) as c:
        r = await c.post("/v1/ideas/diagnose", json=IDEA, headers=AUTH)
    body = r.json()
    assert r.status_code == 200 and body["status"] == "ok"
    assert set(body) == {
        "notice",
        "status",
        "card",
        "lines",
        "signal_labels",
        "reason",
        "reason_label",
        "provider",
        "model",
        "fallback_local",
        "seconds",
    }
    card = body["card"]
    assert card["function_ko"]["value"] == IDEA["goal"]
    assert card["function_ko"]["basis"] == "근거 있음" and card["function_ko"]["origin"] == "ai"
    assert card["contradiction"]["principles"][0] == {"number": 10, "name": "선행 조치"}
    assert set(body["lines"]) == {"function", "cause", "contradiction", "codes"}
    assert body["lines"]["function"] == IDEA["goal"] and " ↔ " in body["lines"]["contradiction"]
    assert body["signal_labels"] == [
        {"signal": "unclear_cause", "label": "원인이 뚜렷하지 않거나 여러 가지"}
    ]
    assert body["fallback_local"] is False and body["reason_label"] is None


async def test_diagnose_requires_auth_and_rejects_unknown_or_empty_fields(tmp_path):
    app, _ = app_for(tmp_path)
    async with client_for(app) as c:
        assert (await c.post("/v1/ideas/diagnose", json=IDEA)).status_code == 401
        r = await c.post("/v1/ideas/diagnose", json={**IDEA, "policy_basis": "x"}, headers=AUTH)
        assert r.status_code == 422
        r = await c.post("/v1/ideas/diagnose", json={**IDEA, "goal": " "}, headers=AUTH)
        assert r.status_code == 422
        assert "필수 슬롯이 비었습니다: goal" in r.json()["detail"]
        r = await c.post("/v1/ideas/diagnose", json={**IDEA, "previous": {"nope": 1}}, headers=AUTH)
        assert r.status_code == 422


async def test_diagnose_keeps_user_items_of_previous_card(tmp_path):
    app, _ = app_for(tmp_path)
    async with client_for(app) as c:
        card = (await c.post("/v1/ideas/diagnose", json=IDEA, headers=AUTH)).json()["card"]
        card["function_ko"].update(value="조류의 착좌를 막는다", origin="user")
        r = await c.post("/v1/ideas/diagnose", json={**IDEA, "previous": card}, headers=AUTH)
    again = r.json()["card"]
    assert again["function_ko"]["value"] == "조류의 착좌를 막는다"
    assert again["function_ko"]["origin"] == "user" and again["function_en"]["origin"] == "ai"


async def test_edit_applies_user_field_and_reports_reruns(tmp_path):
    app, parts = app_for(tmp_path, who=lambda request: STAFF)
    async with client_for(app) as c:
        before = (await c.post("/v1/ideas/diagnose", json=IDEA, headers=AUTH)).json()["card"]
        after = {**before, "causes": [{**before["causes"][0], "value": "천장 틈새가 넓어 드나듦"}]}
        r = await c.post(
            "/v1/ideas/diagnose/edit",
            json={"request": IDEA, "before": before, "after": after, "fields": ["cause"]},
            headers=AUTH,
        )
        body = r.json()
        assert r.status_code == 200
        assert set(body) == {
            "notice",
            "card",
            "lines",
            "signal_labels",
            "reruns",
            "plans_stale",
            "recorded",
        }
        assert body["card"]["causes"][0]["origin"] == "user"
        assert body["card"]["causes"][0]["ai_value"] == IDEA["root_cause"]
        assert body["lines"]["cause"] == "천장 틈새가 넓어 드나듦"
        assert body["reruns"] == ["checks", "clarify"] and body["plans_stale"] is False
        assert body["recorded"] is True
        assert parts["edit_log"].by_user(STAFF.id)[0]["field"] == "cause"
        assert parts["choice_log"].records[0]["event"] == "card_edit"

        after = {**before, "function_ko": {**before["function_ko"], "value": "조류 착좌를 막는다"}}
        r = await c.post(
            "/v1/ideas/diagnose/edit",
            json={
                "request": IDEA,
                "before": before,
                "after": after,
                "fields": ["function_ko", "function_ko"],
            },
            headers=AUTH,
        )
        body = r.json()
        assert body["reruns"] == ["derive", "analogy", "plans_stale"]
        assert body["plans_stale"] is True
        assert body["card"]["function_ko"]["origin"] == "user"


async def test_edit_by_guest_is_applied_but_not_recorded(tmp_path):
    app, parts = app_for(tmp_path, who=lambda request: GUEST)
    async with client_for(app) as c:
        before = (await c.post("/v1/ideas/diagnose", json=IDEA, headers=AUTH)).json()["card"]
        after = {**before, "causes": [{**before["causes"][0], "value": "천장 틈새가 넓어 드나듦"}]}
        r = await c.post(
            "/v1/ideas/diagnose/edit",
            json={"request": IDEA, "before": before, "after": after, "fields": ["cause"]},
            headers=AUTH,
        )
    assert r.json()["recorded"] is False and r.json()["card"]["causes"][0]["origin"] == "user"
    assert parts["edit_log"].records == [] and parts["choice_log"].records == []


async def test_edit_validation_and_disabled(tmp_path):
    app, _ = app_for(tmp_path / "on")
    async with client_for(app) as c:
        card = (await c.post("/v1/ideas/diagnose", json=IDEA, headers=AUTH)).json()["card"]
        body = {"request": IDEA, "before": card, "after": card, "fields": ["cause"]}
        for bad in (
            {**body, "fields": []},
            {**body, "fields": ["title"]},
            {**body, "extra": 1},
            {**body, "request": {**IDEA, "x": 1}},
        ):
            assert (
                await c.post("/v1/ideas/diagnose/edit", json=bad, headers=AUTH)
            ).status_code == 422
        r = await c.post(
            "/v1/ideas/diagnose/edit",
            json={**body, "request": {**IDEA, "root_cause": ""}},
            headers=AUTH,
        )
        assert r.status_code == 422 and "root_cause" in r.json()["detail"]
    for i, kw in enumerate(({"enabled": False}, {"wired": False})):
        app, _ = app_for(tmp_path / f"off{i}", **kw)
        async with client_for(app) as c:
            r = await c.post("/v1/ideas/diagnose/edit", json=body, headers=AUTH)
        assert r.status_code == 409
        assert "run" not in r.json()["detail"]


def test_composition_builds_port_implementations_and_off_by_default(tmp_path):
    from rra.application.usecases.problem_card_contract import (
        CardEditLogPort,
        CardEditor,
        ClassCodeCheck,
        ProblemDiagnosis,
    )

    settings = settings_for(tmp_path, enabled=False)
    repo, llm = InMemoryRepository(), ScriptedComposeLLM()
    diagnosis = composition.build_problem_diagnosis(settings, repo=repo, llm=llm)
    assert isinstance(diagnosis, ProblemDiagnosis) and diagnosis.config.enabled is False
    assert diagnosis.max_tokens == 1500 and diagnosis.embedding is None
    assert isinstance(composition.build_card_editor(settings, repo=repo, llm=llm), CardEditor)
    assert isinstance(composition.build_card_edit_log(settings), CardEditLogPort)
    assert isinstance(composition.build_class_code_check(settings, repo=repo), ClassCodeCheck)
    assert not (tmp_path / "data").exists()  # 가짜 모드는 데이터 폴더를 건드리지 않는다
    stored = yaml.safe_load(Path("config/problem_card.yaml").read_text(encoding="utf-8"))
    assert stored["enabled"] is False  # 저장소 값은 꺼짐 그대로
