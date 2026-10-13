"""Agent 의 Tool 호출 조건 — 기획서 Ⅲ 표의 여섯 행."""

from rra.domain.models import OverlapAlert, ProposalRequest
from rra.domain.rules import agent_policy as policy

REQ = ProposalRequest(current_state="a", root_cause="b", limitation="c", goal="d")
WITH_BASIS = REQ.model_copy(update={"policy_basis": "국가철도망 구축계획"})


def alert(blocking: bool) -> OverlapAlert:
    return OverlapAlert(doc_id="alio:1", title="t", tier="own", similarity=0.9, blocking=blocking)


def test_intake_calls_precheck_first():
    d = policy.on_intake()
    assert d.tool == "rra_precheck" and "아이디어 입력" in d.condition


def test_blocking_alert_requires_human_before_generate():
    [first, *_] = policy.after_precheck([alert(True)], WITH_BASIS, corpus_size=5)
    assert first.needs_human and first.tool is None and "차단" in first.condition
    assert not policy.may_generate([alert(True)], acknowledged=False)
    assert policy.may_generate([alert(True)], acknowledged=True)


def test_no_alert_or_acknowledged_generates():
    [d] = policy.after_precheck([alert(False)], WITH_BASIS, corpus_size=5)
    assert d.tool == "rra_generate" and not d.needs_human
    [d2] = policy.after_precheck([alert(True)], WITH_BASIS, corpus_size=5, acknowledged=True)
    assert d2.tool == "rra_generate"


def test_missing_policy_basis_is_announced():
    decisions = policy.after_precheck([], REQ, corpus_size=5)
    assert [d.condition for d in decisions] == [
        "경보 없음 또는 담당자가 진행 선택",
        "정책 근거 미입력",
    ]
    assert all(d.tool != "rra_generate" for d in decisions[1:])


def test_empty_corpus_is_announced():
    decisions = policy.after_precheck([], WITH_BASIS, corpus_size=0)
    assert decisions[-1].condition == "비교할 수집 자료 없음" and decisions[-1].tool is None


def test_query_and_confirm_tools():
    assert policy.on_query().tool == "rra_search"
    assert policy.on_confirm().tool == "rra_confirm"
