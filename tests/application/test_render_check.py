"""렌더 전 점검 (application/usecases/render_check.py) — 순수 함수 + RunManager.render_check.

렌더를 막지 않는 알림 목록: 저장된 lint 문제(미해결), 본문 max_chars·한 줄 칸 line_limits 초과,
전략 목록 빈칸. 제안자 정보는 길이만 재고 저장되지 않는다.
"""

import pytest

from rra.application.usecases.render_check import (
    STRATEGY_EMPTY,
    STRATEGY_UNCONFIRMED,
    RenderCheck,
    render_check,
)
from rra.domain.models import (
    Budget,
    Confirmation,
    Draft,
    ProposalRequest,
    ProposerInfo,
    Section,
    Sentence,
)
from rra.domain.models.proposer import Person
from rra.domain.rules.lint import ChoiceSpec, LintRules

RULES = LintRules(
    sections=["title", "method", "strategy_alignment"],
    required_sections=["title", "method"],
    max_chars={"method": 20},
    choices={"strategy_alignment": ChoiceSpec(options="strategy_catalog", max=2)},
)
LIMITS = {"title": 10, "budget.account": 5, "proposer.name": 3, "strategy_alignment:task": 6}
# title 10 은 무시된다 — 연구과제명은 길이 제한 없음


def draft(title="짧은 제목", method="방법 문장", budget=None, department=""):
    req = ProposalRequest(
        current_state="현황",
        root_cause="원인",
        limitation="한계",
        goal="목표",
        budget=budget,
        department=department,
    )
    return Draft(
        run_id="20260101000000-deadbeef",
        request=req,
        sections=[
            Section(key="title", sentences=[Sentence(text=title)]),
            Section(key="method", sentences=[Sentence(text=method)]),
        ],
    )


def test_clean_draft_has_no_notices_when_strategy_is_confirmed():
    check = render_check(
        draft(),
        [],
        RULES,
        confirmation=Confirmation(choices={"strategy_alignment": ["D1-1"]}),
        proposer=None,
        line_limits=LIMITS,
        strategy_labels={"D1-1": "예방정비"},
    )
    assert check == RenderCheck() and check.count == 0


def test_stored_lint_problems_are_all_unresolved_and_kept_in_order():
    problems = [
        {
            "section": "method",
            "code": "unsupported_number",
            "message": "15%",
            "severity": "warning",
        },
        {
            "section": "strategy_alignment",
            "code": "catalog_empty",
            "message": "비어 둠",
            "severity": "warning",
        },
    ]
    check = render_check(
        draft(),
        problems,
        RULES,
        confirmation=None,
        proposer=None,
        line_limits={},
        strategy_labels={},
    )
    assert [p.code for p in check.unresolved] == ["unsupported_number", "catalog_empty"]
    assert check.unresolved[0].severity == "warning" and check.unresolved[0].sentence is None
    assert check.notes == [STRATEGY_EMPTY] and check.count == 3


def test_overflow_lists_section_and_single_line_slots_without_truncating():
    long_title = "가" * 12
    d = draft(
        title=long_title,
        method="아주 긴 연구 방법 문장이 스무 자를 넘습니다 확실히",
        budget=Budget(account="연구개발비용과목", amount_thousand_krw=1234567),
    )
    proposer = ProposerInfo(proposer=Person(name="홍길동전"), head=Person(name="김"))
    check = render_check(
        d,
        [],
        RULES,
        confirmation=Confirmation(choices={"strategy_alignment": ["D1-1", "D1-2"]}),
        proposer=proposer,
        line_limits=LIMITS,
        strategy_labels={"D1-1": "예방정비", "D1-2": "안전투자"},
    )
    by_slot = {o.slot: o for o in check.overflow}
    assert by_slot["method"].kind == "section" and by_slot["method"].limit == 20
    assert "title" not in by_slot  # 연구과제명은 길이 제한 없음 — 설정에 있어도 알림을 내지 않는다
    assert by_slot["budget.account"].chars == 8 and by_slot["proposer.name"].chars == 4
    assert by_slot["strategy_alignment:task"].chars == len("예방정비, 안전투자")
    assert "head.name" not in by_slot and check.notes == []
    # 길이를 넘어도 초안·입력은 그대로 (자르지 않는다)
    assert d.section("title").text == long_title


def test_strategy_note_distinguishes_empty_catalog_from_unconfirmed():
    empty = render_check(
        draft(), [], RULES, confirmation=None, proposer=None, line_limits={}, strategy_labels={}
    )
    unconfirmed = render_check(
        draft(),
        [],
        RULES,
        confirmation=Confirmation(choices={"task_type": ["basic"]}),
        proposer=None,
        line_limits={},
        strategy_labels={"D1-1": "예방정비"},
    )
    no_strategy_rules = LintRules(sections=["title"], required_sections=["title"])
    none = render_check(
        draft(),
        [],
        no_strategy_rules,
        confirmation=None,
        proposer=None,
        line_limits={},
        strategy_labels={},
    )
    assert empty.notes == [STRATEGY_EMPTY]
    assert unconfirmed.notes == [STRATEGY_UNCONFIRMED]
    assert none.notes == []


@pytest.mark.asyncio
async def test_run_manager_render_check_uses_stored_problems_and_keeps_proposer_out(monkeypatch):
    import json

    from tests.entrypoints.ui.fake_app import make_assistant

    assistant = make_assistant()
    mgr = assistant.manager
    mgr.line_limits = {"proposer.name": 2}
    req = ProposalRequest(
        current_state="경부선 궤도 틀림 반복",
        root_cause="노반 침하",
        limitation="임계치만",
        goal="예측",
    )
    state = await mgr.submit(assistant.user, req)
    await mgr.wait(assistant.user, state.run_id)
    proposer = ProposerInfo(proposer=Person(name="홍길동"))
    check = await mgr.render_check(assistant.user, state.run_id, proposer=proposer)
    assert any(p.code == "unsupported_number" for p in check.unresolved)  # finalize 가 남긴 경고
    assert STRATEGY_EMPTY in check.notes  # 전략 목록 비어 있음
    assert [o.slot for o in check.overflow] == ["proposer.name"]
    dumped = json.dumps({k: str(v) for k, v in vars(mgr.store).items()}, ensure_ascii=False)
    assert "홍길동" not in dumped  # 저장소 어디에도 없다


def test_long_title_is_never_a_notice():
    long_title = (
        "경부선 궤도 검측 이력 기반 궤도 틀림 열화 예측 및 다짐 효과를 반영한 "
        "보수 우선순위 산정 방법 개발 연구"
    )
    assert len(long_title) >= 60
    check = render_check(
        draft(title=long_title),
        [],
        RULES,
        confirmation=Confirmation(choices={"strategy_alignment": ["D1-1"]}),
        proposer=None,
        line_limits={"title": 30, **LIMITS},
        strategy_labels={"D1-1": "예방정비"},
    )
    assert check.overflow == [] and check.count == 0
