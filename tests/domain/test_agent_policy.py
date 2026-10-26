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
    [d, near] = policy.after_precheck([alert(False)], WITH_BASIS, corpus_size=5)
    assert d.tool == "rra_generate" and not d.needs_human
    assert near.tool == "rra_differentiate"  # 0.9 는 own 임계치(0.80)의 90% 이상 → 근접
    [d2, _] = policy.after_precheck([alert(True)], WITH_BASIS, corpus_size=5, acknowledged=True)
    assert d2.tool == "rra_generate"


def test_differentiate_row_only_for_blocking_or_near_threshold_alerts():
    far = OverlapAlert(doc_id="x:1", title="t", tier="external", similarity=0.5, blocking=False)
    assert [d.tool for d in policy.after_precheck([far], WITH_BASIS, corpus_size=5)] == [
        "rra_generate"
    ]
    near = OverlapAlert(doc_id="x:2", title="t", tier="external", similarity=0.81, blocking=False)
    near_rows = policy.after_precheck([near], WITH_BASIS, corpus_size=5)
    assert [d.tool for d in near_rows] == ["rra_generate", "rra_differentiate"]  # 0.90 × 0.9 = 0.81
    assert near_rows[1].needs_human and "누르면" in near_rows[1].action  # 근접만 → 담당자 요청 시
    blocked = policy.after_precheck([alert(True)], WITH_BASIS, corpus_size=5)
    assert [d.tool for d in blocked] == [None, "rra_differentiate"] and blocked[0].needs_human
    assert not blocked[1].needs_human and "자동" in blocked[1].action  # 차단 → 자동
    d = policy.on_differentiate()
    assert d.tool == "rra_differentiate" and "차단" in d.condition and not d.needs_human


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


def test_review_edit_finalize_rows():
    from rra.domain.rules import agent_policy as policy

    auto = policy.after_draft_done(review_available=True)
    assert auto.tool == "rra_review" and "1차" in auto.action and not auto.needs_human
    manual = policy.after_draft_done(review_available=True, auto=False)
    assert manual.tool == "rra_review" and manual.needs_human
    skipped = policy.after_draft_done(review_available=False)
    assert skipped.tool is None and "review_skipped" in skipped.action
    again = policy.on_edit(rereview=True, round_no=2)
    assert again.tool == "rra_review" and "3차" in again.action
    assert policy.on_edit(rereview=False, round_no=1).tool == "rra_edit"
    assert policy.on_finalize().tool == "rra_finalize" and policy.on_reopen().tool == "rra_reopen"
