"""제안자 입력 — 검색·유사과제 판정 질의는 현황·원인·한계·목표(+가제)만 쓴다.

필수 슬롯 규칙은 도메인 한 곳(REQUIRED_SLOTS)에만 있고, 진입점은 메시지로 바꾸기만 한다.
"""

import pytest
from pydantic import ValidationError

from rra.domain.models import ProposalRequest
from rra.domain.models.request import (
    MISSING_SLOTS_MESSAGE,
    REQUIRED_SLOTS,
    missing_required_slots,
    validation_message,
)

FULL = {"current_state": "현황", "root_cause": "원인", "limitation": "한계", "goal": "목표"}


def test_search_text_excludes_constraints_and_form_fields():
    req = ProposalRequest(
        current_state="궤도 틀림 반복",
        root_cause="노반 침하",
        limitation="임계치만 봄",
        goal="열화 속도 추정",
        constraints="연구기간 1년 이내, 추가 센서 없음",
        title_hint="궤도 열화 예측",
        policy_basis="국가철도망 구축계획",
        beneficiaries="시설처",
        remarks="특이사항",
        department="철도연구원",
    )
    q = req.search_text()
    assert q == "궤도 열화 예측 궤도 틀림 반복 노반 침하 임계치만 봄 열화 속도 추정"
    for absent in ("연구기간", "센서", "국가철도망", "시설처", "특이사항", "철도연구원"):
        assert absent not in q


# ── 필수 슬롯 ──────────────────────────────────────────────


@pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
@pytest.mark.parametrize("slot", REQUIRED_SLOTS)
def test_blank_required_slot_is_rejected_by_the_model(slot, blank):
    with pytest.raises(ValidationError) as info:
        ProposalRequest(**{**FULL, slot: blank})
    msg = validation_message(info.value)
    assert msg == f"{MISSING_SLOTS_MESSAGE}: {slot}"


def test_all_missing_slots_are_listed_in_order():
    with pytest.raises(ValidationError) as info:
        ProposalRequest(current_state="x")
    expected = f"{MISSING_SLOTS_MESSAGE}: root_cause, limitation, goal"
    assert validation_message(info.value) == expected
    assert missing_required_slots({"current_state": "x"}) == ["root_cause", "limitation", "goal"]


def test_validation_message_relabels_slots_and_strips_pydantic_prefix():
    with pytest.raises(ValidationError) as info:
        ProposalRequest(**{**FULL, "goal": ""})
    labelled = validation_message(info.value, {"goal": "해결 목표"})
    assert labelled == f"{MISSING_SLOTS_MESSAGE}: 해결 목표"
    with pytest.raises(ValidationError) as info:
        ProposalRequest(**{**FULL, "goal": "가" * 2001})
    assert validation_message(info.value) == "goal: 슬롯 길이 2001 > 2000"


def test_optional_fields_may_stay_blank():
    req = ProposalRequest(**FULL)
    assert req.constraints == "" and req.budget is None
