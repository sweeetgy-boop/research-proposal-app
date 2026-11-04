"""[유사함] 한 규칙(ADR 0054) — REST·CLI·MCP·Streamlit 이 같은 함수(usecases/similar_rows)를 거친다.

같은 알림(fixture)을 네 진입점의 과제안(추천)·활용 제안 경로에 넣고, [유사함] 행·'새 영역' 다시
받기·보낸 문서가 모두 같은지, 그리고 그때마다 similar_rows 가 불렸는지 본다. 가짜 LLM 만 쓴다.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
import yaml

from rra.application.usecases import similar_rows as rows_mod
from rra.application.usecases.differentiate import Differentiate
from rra.application.usecases.precheck_overlap import PrecheckOverlap
from rra.application.usecases.recommend_projects import RecommendProjects
from rra.domain.models import OverlapAlert, ProposalRequest, RetrievalSnapshot
from rra.domain.rules.differentiation import candidates
from rra.entrypoints import cli
from rra.entrypoints.mcp.run_tools import RraRunTools
from tests.application.test_recommend_projects import CHUNKS, DOCS, reply
from tests.entrypoints.test_api import AUTH, build
from tests.entrypoints.test_cli import SLOT_ARGS
from tests.entrypoints.ui.fake_app import make_assistant
from tests.fakes import FakeLLM, FakePromptLibrary, InMemoryRepository

SLOTS = {
    "current_state": "궤도 틀림 점검이 수작업",
    "root_cause": "센서 부재",
    "limitation": "주기 점검만 가능",
    "goal": "상시 자동 감지",
}  # tests/entrypoints/test_cli.SLOT_ARGS 와 같은 입력
REQ = ProposalRequest(**SLOTS)


def _alert(doc_id, *, judgment=None, judged_by=None, blocking=False, similarity=0.86):
    return OverlapAlert(
        doc_id=doc_id,
        title=doc_id,
        tier="own",
        similarity=similarity,
        blocking=blocking,
        judgment=judgment,
        judged_by=judged_by,
    )


# AI 판정: own:1 일부 겹침(→ [유사함]), alio:sum-1 다르다(→ [관련 없음])
JUDGED = [
    _alert("own:1", judgment="partial", judged_by="argon"),
    _alert("alio:sum-1", judgment="different", judged_by="argon"),
]
# 규칙 판정만(AI 판정 없음, 선택 없음) — 유사함 0건. own:1 은 규칙 차단
RULE_ONLY = [
    _alert("own:1", judged_by="rule", blocking=True, similarity=0.9),
    _alert("alio:sum-1", judged_by="rule"),
]


class StubPrecheck:
    def __init__(self, alerts):
        self.alerts = alerts
        self.repo = None

    async def __call__(self, req):
        return list(self.alerts)


class _Closable(FakeLLM):
    async def aclose(self):
        return None


def _repo():
    repo = InMemoryRepository()
    repo.seed(DOCS, CHUNKS)
    return repo


def _recommender():
    async def retrieve(req):
        return RetrievalSnapshot.of(req.search_text(), list(CHUNKS))

    return RecommendProjects(
        _Closable([reply([], reason="이미 다름"), reply([], reason="여전히 다름")]),
        FakePromptLibrary(),
        _repo(),
        precheck=StubPrecheck([]),
        retrieve=retrieve,
    )


def _differentiator():
    return Differentiate(_Closable(["[]", "[]"]), FakePromptLibrary(), _repo())


@pytest.fixture
def spy(monkeypatch):
    """usecases/similar_rows 의 규칙 입구 호출 수."""
    calls = {"n": 0}
    real = rows_mod.effective_similar

    def counting(alerts, choices):
        calls["n"] += 1
        return real(alerts, choices)

    monkeypatch.setattr(rows_mod, "effective_similar", counting)
    return calls


def _wire_cli(monkeypatch, alerts, recommender, differentiator):
    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr("rra.composition.build_precheck", lambda *a, **k: StubPrecheck(alerts))
    monkeypatch.setattr("rra.composition.build_recommender", lambda *a, **k: recommender)
    monkeypatch.setattr("rra.composition.build_differentiator", lambda *a, **k: differentiator)


def _sent(transfer):
    return sorted([*transfer["public_doc_ids"], *transfer["internal_doc_ids"]])


async def _rest(alerts):
    assistant = make_assistant(differentiate=None, recommend=None)
    assistant.precheck = StubPrecheck(alerts)
    app, _ = build(
        assistant,
        recommend=_recommender(),
        differentiate=_differentiator(),
        recommend_auto=False,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    ) as c:
        rec = (await c.post("/v1/precheck/recommendations", json=SLOTS, headers=AUTH)).json()
        view = (await c.post("/v1/precheck/choices", json=SLOTS, headers=AUTH)).json()
        diff = (await c.post("/v1/precheck/differentiate", json=SLOTS, headers=AUTH)).json()
    return rec["recommendations"], view["similar_count"], diff["differentiation"]


async def _cli(monkeypatch, capsys, alerts):
    """CLI 는 asyncio.run 을 쓰므로 이벤트 루프 밖(스레드)에서 부른다."""
    _wire_cli(monkeypatch, alerts, _recommender(), _differentiator())
    capsys.readouterr()
    code = await asyncio.to_thread(cli.main, ["recommend", *SLOT_ARGS, "--json"])
    assert code == cli.EXIT_OK
    rec = json.loads(capsys.readouterr().out)
    code = await asyncio.to_thread(cli.main, ["differentiate", *SLOT_ARGS, "--json"])
    assert code == cli.EXIT_OK
    diff = json.loads(capsys.readouterr().out)
    return rec, diff


async def _mcp(alerts):
    tools = RraRunTools(
        object(),
        "local",
        precheck=StubPrecheck(alerts),
        recommend=_recommender(),
        differentiate=_differentiator(),
    )
    return await tools.recommend(**SLOTS), await tools.differentiate(**SLOTS)


async def _streamlit(alerts):
    assistant = make_assistant(differentiate=_differentiator(), recommend=_recommender())
    rec = await assistant.recommend(REQ, list(alerts))
    diff = await assistant.differentiate(REQ, list(alerts))
    return rec, diff


async def test_ai_partial_row_is_similar_everywhere_and_no_new_area_retry(monkeypatch, capsys, spy):
    expected = [a.doc_id for a in rows_mod.similar_rows(JUDGED, {})]
    assert expected == ["own:1"] and rows_mod.similar_count(JUDGED, {}) == 1

    before = spy["n"]
    rest_rec, rest_count, rest_diff = await _rest(JUDGED)
    assert spy["n"] > before
    before = spy["n"]
    cli_rec, cli_diff = await _cli(monkeypatch, capsys, JUDGED)
    assert spy["n"] > before
    before = spy["n"]
    mcp_rec, mcp_diff = await _mcp(JUDGED)
    assert spy["n"] > before
    before = spy["n"]
    ui_rec, ui_diff = await _streamlit(JUDGED)
    assert spy["n"] > before

    assert rest_count == 1
    similar = [
        rest_rec["similar_doc_ids"],
        cli_rec["similar_doc_ids"],
        mcp_rec["similar_doc_ids"],
        ui_rec.similar_doc_ids,
    ]
    assert similar == [expected] * 4
    # AI '일부 겹침' 행이 [유사함] 이므로 0건이어도 '새 영역' 다시 받기는 없다
    retry = [
        rest_rec["retry_used"],
        cli_rec["retry_used"],
        mcp_rec["retry_used"],
        ui_rec.retry_used,
    ]
    assert retry == [False] * 4
    # 활용 제안 대상도 같은 행
    sent = [
        _sent(rest_diff["transfer"]),
        _sent(cli_diff["transfer"]),
        _sent(mcp_diff["transfer"]),
        sorted([*ui_diff.public_doc_ids, *ui_diff.internal_doc_ids]),
    ]
    assert sent == [expected] * 4


async def test_no_ai_verdict_and_no_choice_is_zero_similar_and_retries_everywhere(
    monkeypatch, capsys, spy
):
    assert rows_mod.similar_count(RULE_ONLY, {}) == 0
    rest_rec, rest_count, rest_diff = await _rest(RULE_ONLY)
    cli_rec, cli_diff = await _cli(monkeypatch, capsys, RULE_ONLY)
    mcp_rec, mcp_diff = await _mcp(RULE_ONLY)
    ui_rec, ui_diff = await _streamlit(RULE_ONLY)

    assert rest_count == 0
    similar = [
        rest_rec["similar_doc_ids"],
        cli_rec["similar_doc_ids"],
        mcp_rec["similar_doc_ids"],
        ui_rec.similar_doc_ids,
    ]
    assert similar == [[]] * 4
    retry = [
        rest_rec["retry_used"],
        cli_rec["retry_used"],
        mcp_rec["retry_used"],
        ui_rec.retry_used,
    ]
    assert retry == [True] * 4
    # 활용 제안: REST(선택 화면)는 [유사함] 이 없으면 건너뛴다. 선택 화면이 없는 진입점은 AI 판정도
    # 선택도 없을 때만 종전 후보(규칙 차단)를 쓴다 — 셋 다 같은 함수(differentiation_rows)
    assert rest_diff["skipped_reason"] == "no_similar_selected"
    legacy = [
        _sent(cli_diff["transfer"]),
        _sent(mcp_diff["transfer"]),
        sorted([*ui_diff.public_doc_ids, *ui_diff.internal_doc_ids]),
    ]
    rule = sorted(a.doc_id for a in candidates(RULE_ONLY))
    assert "own:1" in rule and legacy == [rule] * 3


async def test_stage_full_differentiate_trigger_uses_the_same_count():
    """/v1/precheck stage=full — [유사함] 이 AI 기본 선택뿐이어도 활용 제안을 붙인다."""
    for alerts, expected in ((JUDGED, True), (RULE_ONLY, False)):
        assistant = make_assistant(differentiate=None, recommend=None)
        assistant.precheck = StubPrecheck(alerts)
        app, _ = build(assistant, differentiate=_differentiator(), recommend_auto=False)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
        ) as c:
            body = (await c.post("/v1/precheck", json=SLOTS, headers=AUTH)).json()
        assert body["similar_count"] == int(expected)
        assert ("differentiation" in body) is expected


async def test_golden_03_unrelated_idea_stays_zero_blocking_and_zero_similar(docs, own):
    """골든셋 03(철도 무관 — 차단 0건이 정답)은 새 규칙에서도 차단 0·[유사함] 0·기본 선택 없음."""
    path = Path(__file__).resolve().parents[1] / "golden" / "03_unrelated_library.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.pop("expected_similar")
    req = ProposalRequest(**data)
    repo = InMemoryRepository()
    repo.seed(docs, [])
    result = await PrecheckOverlap(repo, own=own).run(req)
    assert [a for a in result.alerts if a.blocking] == []
    assert rows_mod.similar_count(result.alerts, req.choice_map()) == 0
    assert rows_mod.default_choice_list(result.alerts) == []
