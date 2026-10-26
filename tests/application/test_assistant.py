"""ProposalAssistant — 기획서 Tool 호출 조건대로 유스케이스를 부르고 trace 에 남긴다. FakeLLM 만."""

import pytest

from rra.application.services import HumanConfirmationRequired
from rra.domain.models import ProposalRequest
from tests.entrypoints.ui.fake_app import METHOD_SENTENCE, make_assistant

REQ = ProposalRequest(
    current_state="궤도 틀림 반복",
    root_cause="노반 침하",
    limitation="임계치만 봄",
    goal="열화 예측",
)


async def test_intake_runs_precheck_and_announces_conditions():
    a = make_assistant(blocking=True)
    res = await a.intake(REQ)
    assert [x.blocking for x in res.alerts] == [True]
    assert res.decisions[0].needs_human and "정책 근거 미입력" in [
        d.condition for d in res.decisions
    ]
    assert res.uncollected == ["scienceon", "kipris_kr", "kipris_intl", "ntis", "own"]
    assert [t.tool for t in a.trace] == [
        "rra_precheck",
        None,
        None,
        "rra_differentiate",
        "rra_recommend",
    ]
    assert "차단 1건" in a.trace[0].summary
    assert res.differentiation is not None and res.differentiation.items  # 차단 → 자동 차별화 제안


async def test_intake_without_blocking_does_not_run_differentiation_automatically():
    a = make_assistant(blocking=False)
    res = await a.intake(REQ)
    assert res.differentiation is None and all(t.tool != "rra_differentiate" for t in a.trace)


async def test_blocking_without_acknowledgement_does_not_generate():
    a = make_assistant(blocking=True)
    res = await a.intake(REQ)
    with pytest.raises(HumanConfirmationRequired):
        await a.proceed(REQ, res.alerts, acknowledged=False)
    assert all(t.tool != "rra_generate" for t in a.trace)


async def test_acknowledged_generation_runs_to_done_and_polls_are_logged_once_per_status():
    a = make_assistant(blocking=True)
    res = await a.intake(REQ)
    state = await a.proceed(REQ, res.alerts, acknowledged=True)
    assert state.status == "queued" and "차단 경보 확인 후" in a.trace[-1].summary
    final = await a.manager.wait(a.user, state.run_id)
    assert final.status == "drafted"
    await a.poll(state.run_id)
    await a.poll(state.run_id)
    polls = [t for t in a.trace if t.tool == "rra_get_draft"]
    assert len(polls) == 1 and "drafted" in polls[0].summary
    view = await a.poll(state.run_id)
    assert METHOD_SENTENCE in [s.text for s in view.sections[2].sentences]
    assert any(p["code"] == "unsupported_number" for p in view.state.problems)


async def test_search_and_confirm_are_logged():
    a = make_assistant()
    res = await a.intake(REQ)
    assert res.alerts == [] and res.decisions[0].tool == "rra_generate"
    chunks = await a.ask("궤도", k=50)
    assert len(chunks) == 2 and a.trace[-1].tool == "rra_search" and "k=10" in a.trace[-1].summary
    assert await a.ask("   ") == []
    state = await a.proceed(REQ, [], acknowledged=False)
    await a.manager.wait(a.user, state.run_id)
    confirmation = await a.confirm(state.run_id, {"task_type": ["basic"]})
    assert confirmation.choices == {"task_type": ["basic"]} and a.trace[-1].tool == "rra_confirm"
