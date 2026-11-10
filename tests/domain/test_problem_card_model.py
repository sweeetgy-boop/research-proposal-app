"""문제 정의 카드 계약 모델 (ADR 0065, 0단계) — 형식·기본값·요청 연결."""

import pytest
from pydantic import ValidationError

from rra.config_loader import problem_card_config
from rra.domain.models import ProposalRequest
from rra.domain.models.problem_card import (
    CARD_DEPENDENTS,
    CARD_FIELDS,
    CardText,
    ClassCode,
    LadderStep,
    ProblemCard,
    ProblemCardConfig,
    ProblemTerms,
)
from rra.domain.models.request import FORM_ONLY_FIELDS
from rra.domain.rules.live_search import keyword_cache_key
from rra.settings import Settings

IDEA = {
    "title_hint": "철도역사 비둘기 침입 방지",
    "current_state": "역사 승강장 지붕에 비둘기가 드나들어 배설물 민원이 반복됨",
    "root_cause": "출입구가 열려 있어 비둘기 침입 경로가 막히지 않음",
    "limitation": "그물 설치는 미관을 해치고 유지관리가 어려움",
    "goal": "역사 구조에 맞는 비둘기 침입 방지 방법을 마련함",
}


def card() -> ProblemCard:
    return ProblemCard(
        function_ko=CardText(value="조류가 구조물에 앉거나 둥지를 틀지 못하게 막는다"),
        ladder=[
            LadderStep(level="추상화", text="유해동물의 구조물 접근 차단"),
            LadderStep(level="구체", text="비둘기 착좌·둥지 방지"),
            LadderStep(level="일반화", text="조류 접근 방지 장치"),
        ],
        terms=ProblemTerms(objects_ko=["비둘기", "조류", "비둘기"], actions_ko=["퇴치", "x"]),
        ipc=[ClassCode(code="a01m 29/00")],
        signals=["few_analogies", "broad_scope"],
    )


def test_defaults_are_empty_and_off():
    assert ProblemCard().function_ko.value == ""
    assert ProblemCard().function_ko.basis == "추정"
    assert ProblemCardConfig().enabled is False
    assert ProblemCardConfig(use={"analogy_rank": True}).uses("analogy_rank") is False


def test_repo_config_is_off_and_valid():
    cfg = problem_card_config(Settings())
    assert cfg.enabled is False
    assert cfg.rank.per_source == 2
    assert all(v is False for v in cfg.conditional.values())


def test_card_normalizes():
    c = card()
    assert [s.level for s in c.ladder] == ["구체", "일반화", "추상화"]
    assert c.terms.objects_ko == ["비둘기", "조류"]
    assert c.terms.actions_ko == ["퇴치"]  # 한 글자 말은 뺀다
    assert c.ipc[0].code == "A01M 29/00"
    assert c.signals == ["broad_scope", "few_analogies"]
    assert CardText(value="a <b>\n c").value == "a b c"


def test_user_fields():
    c = card().model_copy(update={"function_ko": CardText(value="x", origin="user")})
    assert c.user_fields() == ["function_ko"]


def test_limits():
    with pytest.raises(ValidationError):
        ProblemCard(ipc=[ClassCode(code=f"A0{i}B") for i in range(4)])
    with pytest.raises(ValidationError):
        ProblemCard(unknown=1)


def test_dependents_cover_every_field():
    assert set(CARD_DEPENDENTS) == set(CARD_FIELDS)


def test_request_carries_card_without_touching_keys_or_prompts():
    plain = ProposalRequest(**IDEA)
    with_card = ProposalRequest(**IDEA, problem_card=card())
    assert plain.problem_card is None
    assert "problem_card" in FORM_ONLY_FIELDS
    assert with_card.search_text() == plain.search_text()
    assert with_card.prompt_view() == plain.prompt_view()
    assert keyword_cache_key(with_card) == keyword_cache_key(plain)
    again = ProposalRequest.model_validate(with_card.model_dump())
    assert again.problem_card == with_card.problem_card
