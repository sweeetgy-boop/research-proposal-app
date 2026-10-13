"""제안자 입력 — 검색·유사과제 판정 질의는 현황·원인·한계·목표(+가제)만 쓴다."""

from rra.domain.models import ProposalRequest


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
