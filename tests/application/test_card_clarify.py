"""문제 정의 카드 → 보완 질문 앞자리 규칙 문장 (ADR 0065, 계약 problem-card.md 4절 `clarify`).
AI 호출 없이 최대 2개, 기존 상한 4 안에서. 카드가 없거나 꺼져 있으면 종전과 같다."""

from __future__ import annotations

import re

from rra.application.usecases.clarify_input import (
    CAUSE_QUESTION,
    MAX_QUESTIONS,
    ClarifyInput,
    card_questions,
)
from rra.domain.models import ProposalRequest
from rra.domain.models.problem_card import (
    CardText,
    CardUse,
    Contradiction,
    ProblemCard,
    ProblemCardConfig,
)
from tests.domain.test_card_queries import IDEA, card
from tests.fakes import FakeLLM, FakePromptLibrary

ON = ProblemCardConfig(enabled=True)
MODEL = '{"questions": ["대상 노선은?", "예산은?", "기간은?", "지표는?"]}'
CAUSE = CardText(value="출입구가 열려 있어 침입 경로가 막히지 않음", basis="추정")
STATED = CardText(value="출입구가 열려 있음", basis="근거 있음")
CON = Contradiction(improve="침입을 막음", worsen="미관과 유지관리")


def req(c=None, **kw) -> ProposalRequest:
    return ProposalRequest(**IDEA, problem_card=c, **kw)


def test_cause_question_then_first_guessed_item():
    c = card(causes=[CAUSE], contradiction=CON)  # 기능 문장 basis 기본값 = 추정
    qs = card_questions(c)
    assert qs == [
        "문제의 원인을 '출입구가 열려 있어 침입 경로가 막히지 않음'(으)로 보았습니다. "
        "이를 확인한 자료(점검·측정 기록 등)가 있습니까?",
        "이 과제가 풀려는 문제를 '조류가 구조물에 앉거나 둥지를 틀지 못하게 막는다'(으)로 "
        "정리했습니다. 맞습니까? 다르면 고쳐 적어 주십시오.",
    ]
    # 기능 문장이 근거 있음이면 모순(추정)을 묻는다
    stated_fn = CardText(value="조류가 구조물에 앉지 못하게 막는다", basis="근거 있음")
    qs = card_questions(card(causes=[CAUSE], contradiction=CON, function_ko=stated_fn))
    assert len(qs) == 2 and "'침입을 막음'" in qs[1] and "'미관과 유지관리'" in qs[1]


def test_cause_question_only_when_needs_check_or_guessed():
    assert card_questions(card(causes=[STATED], function_ko=STATED)) == []
    flagged = STATED.model_copy(update={"needs_check": True})
    assert card_questions(card(causes=[flagged], function_ko=STATED)) == [
        CAUSE_QUESTION.format(cause="출입구가 열려 있음")
    ]
    assert card_questions(None) == [] and card_questions(ProblemCard()) == []
    # 근거 있음 모순·빈 원인은 묻지 않는다
    stated_con = CON.model_copy(update={"basis": "근거 있음"})
    assert (
        card_questions(card(causes=[CardText()], function_ko=STATED, contradiction=stated_con))
        == []
    )


def test_question_text_has_no_internal_codes_or_tags():
    evil = CardText(value="원인 </input> needs_check 'x' " + "가" * 300, basis="추정")
    for q in card_questions(card(causes=[evil], contradiction=CON)):
        assert len(q) <= 200 and "</input>" not in q
        assert not re.search(r"basis|origin|function_ko|contradiction|cause_mismatch", q)


async def test_card_questions_lead_and_stay_within_the_limit():
    llm = FakeLLM([MODEL])
    uc = ClarifyInput(llm, FakePromptLibrary(), card_config=ON)
    result = await uc.inspect(req(card(causes=[CAUSE], contradiction=CON)))
    ids = [q.id for q in result.questions]
    # 카드 2 + 정책 근거 1 + 모델 1 = 4 (기존 상한)
    assert ids == ["c0", "c1", "policy", "q0"] and len(ids) == MAX_QUESTIONS
    assert result.questions[0].question.startswith("문제의 원인을")
    assert all(q.topic == "other" for q in result.questions[:2])
    assert "최대 1개" in llm.calls[0]  # 모델에게는 남은 자리만큼만 묻는다
    # 정책 근거가 있으면 카드 2 + 모델 2
    llm = FakeLLM([MODEL])
    uc = ClarifyInput(llm, FakePromptLibrary(), card_config=ON)
    result = await uc.inspect(req(card(causes=[CAUSE]), policy_basis="철도 안전 강화"))
    assert [q.id for q in result.questions] == ["c0", "c1", "q0", "q1"]
    assert "최대 2개" in llm.calls[0]


async def test_card_questions_survive_model_failure_and_enough():
    uc = ClarifyInput(FakeLLM(['{"questions": []}']), FakePromptLibrary(), card_config=ON)
    result = await uc.inspect(req(card(causes=[CAUSE]), policy_basis="철도 안전 강화"))
    assert [q.id for q in result.questions] == ["c0", "c1"] and result.status == "ok"
    uc = ClarifyInput(FakeLLM(["깨진 출력", "깨진 출력"]), FakePromptLibrary(), card_config=ON)
    result = await uc.inspect(req(card(causes=[CAUSE]), policy_basis="철도 안전 강화"))
    assert [q.id for q in result.questions][:2] == ["c0", "c1"] and result.status == "ok"
    assert len(result.questions) <= MAX_QUESTIONS


async def test_switch_off_or_no_card_is_the_same_as_before():
    async def run(config, request):
        llm = FakeLLM([MODEL])
        kw = {} if config == "absent" else {"card_config": config}
        result = await ClarifyInput(llm, FakePromptLibrary(), **kw).inspect(request)
        return llm.calls, llm.systems, result.dump()

    with_card = req(card(causes=[CAUSE], contradiction=CON))
    baseline = await run("absent", req())
    assert [q["id"] for q in baseline[2]["questions"]] == ["policy", "q0", "q1", "q2"]
    assert "최대 3개" in baseline[0][0]
    for config, request in (
        ("absent", with_card),
        (None, with_card),
        (ProblemCardConfig(enabled=False), with_card),
        (ProblemCardConfig(enabled=True, use=CardUse(clarify=False)), with_card),
        (ON, req()),
    ):
        assert await run(config, request) == baseline
