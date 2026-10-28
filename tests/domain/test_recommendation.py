"""차별화 과제 추천 규칙 — 검증·중복·상한·사유·입력 반영 (순수 규칙, LLM 없음)."""

from rra.domain.models import ProjectRecommendation, ProposalRequest
from rra.domain.rules import recommendation as rule

REQ = ProposalRequest(
    current_state="경부선 궤도 틀림은 분기별로 측정함",
    root_cause="구간별 진행 속도가 다름",
    limitation="보수 우선순위 근거가 없음",
    goal="운행 차량 센서로 궤도 틀림을 상시 감지함",
)
ALERTS = ["own:1", "alio:sum-1"]
EVIDENCE = ["openalex:W1"]
ALLOWED = [
    *(v for v in REQ.model_dump().values() if isinstance(v, str)),
    "검측차 이력 분석 과제 2023년",
    "Track geometry degradation from inspection history",
]
GOOD = {
    "title": "운행 차량 가속도 기반 궤도 틀림 진행 속도 추정",
    "summary": "검측차 이력에 운행 차량 가속도를 더해 구간별 진행 속도를 추정함",
    "differentiation": "기존 과제는 검측 주기 안의 변화를 보지 못함",
    "reasons": ["own:1 은 검측차 이력 분석에 그침", "openalex:W1 은 센서 비용이 큼"],
    "build_on": "own:1 의 검측 이력 정리 체계를 씀",
    "risks": "센서 설치 승인 확인 필요",
    "compared_with": ["own:1"],
    "evidence": ["own:1", "openalex:W1"],
}


def validate(raw):
    return rule.validate_recommendation(
        raw, alert_doc_ids=ALERTS, evidence_doc_ids=EVIDENCE, allowed_texts=ALLOWED
    )


def test_valid_recommendation_passes_and_is_cleaned():
    rec, reason = validate({**GOOD, "title": GOOD["title"] + ' <doc id="x">'})
    assert reason is None and rec is not None
    assert "<doc" not in rec.title and rec.compared_with == ["own:1"]
    assert rec.evidence == ["own:1", "openalex:W1"] and len(rec.reasons) == 2


def test_missing_core_fields_discard_but_out_of_range_ids_are_only_trimmed():
    assert validate({**GOOD, "title": ""})[1] == rule.DISCARD_EMPTY
    rec, reason = validate({**GOOD, "reasons": []})  # 이유 0개도 허용 (2026-10-28 완화)
    assert reason is None and rec.reasons == []
    rec, reason = validate({**GOOD, "compared_with": ["ntis:zzz", "own:1"]})
    assert reason is None and rec.compared_with == ["own:1"]  # 범위 밖 id 만 빠진다
    rec, reason = validate({**GOOD, "evidence": ["openalex:W9"]})
    assert reason is None and rec.evidence == []
    # compared_with 도 검색 근거 id(논문)를 허용 — 검색으로 찾은 논문도 비교 대상
    assert validate({**GOOD, "compared_with": ["openalex:W1"]})[1] is None


def test_made_up_numbers_policy_names_and_foreign_script_are_discarded():
    assert validate({**GOOD, "summary": "비용을 37% 절감함"})[1] == rule.DISCARD_NUMBER
    assert (
        validate({**GOOD, "summary": "검측차 이력 분석 과제 2023년 결과를 씀"})[1] is None
    )  # 자료에 있는 수치
    # 부가 칸(위험·이유)의 지어낸 정책명은 그 칸만 비운다 — 추천은 남는다
    rec, reason = validate({**GOOD, "risks": "국가철도망 구축계획 반영 필요"})
    assert reason is None and rec.risks == ""
    rec, _ = validate({**GOOD, "reasons": ["국가철도망 구축계획과 다름", "own:1 은 이력만 봄"]})
    assert rec.reasons == ["own:1 은 이력만 봄"]
    assert (
        validate({**GOOD, "summary": "국가철도망 구축계획 반영"})[1] == rule.DISCARD_UNGROUNDED
    )
    assert validate({**GOOD, "differentiation": "軌道 틀림을 봄"})[1] == rule.DISCARD_FOREIGN


def test_card_fields_goal_method_scope_and_labels():
    rec, _ = validate({**GOOD, "goal": "구간별 진행 속도를 추정함", "method": "운행 차량 가속도 분석", "scope": "경부선"})
    assert (rec.goal, rec.method, rec.scope) == ("구간별 진행 속도를 추정함", "운행 차량 가속도 분석", "경부선")
    assert rule.discard_label(rule.DISCARD_NUMBER) == "자료에 없는 수치를 씀"
    assert "unsupported" not in rule.regeneration_hint([{"reason": rule.DISCARD_NUMBER}])


def make(title, summary="요약 문장임", diff="차별점임", **kw):
    return ProjectRecommendation(
        title=title, summary=summary, differentiation=diff, reasons=["이유"], **kw
    )


def test_near_duplicates_collapse_and_limit_is_five():
    a = make("운행 차량 가속도 기반 궤도 틀림 진행 속도 추정", "검측차 이력에 가속도를 더함")
    b = make("운행 차량 가속도 기반 궤도 틀림 진행 속도 추정 방법", "검측차 이력에 가속도를 더함")
    c = make("분기기 마모 예측", "통과 톤수 자료로 분기기 마모를 예측함", "대상 설비가 다름")
    assert rule.near_duplicate(a, b) and not rule.near_duplicate(a, c)
    topics = [
        ("승강장 혼잡도 예측", "승객 흐름 자료로 혼잡을 예측함", "역사 운영 관점임"),
        ("전차선 마모 진단", "전류 자료로 마모를 진단함", "전력 설비 관점임"),
        ("신호기 고장 예지", "로그 자료로 고장을 예지함", "신호 설비 관점임"),
        ("화물 적재 최적화", "운송 자료로 적재를 최적화함", "물류 관점임"),
        ("차량 베어링 진단", "진동 자료로 베어링을 진단함", "차량 관점임"),
        ("터널 누수 감시", "영상 자료로 누수를 감시함", "구조물 관점임"),
    ]
    many = [a, b, c] + [make(t, s_, d) for t, s_, d in topics]
    kept, discarded = rule.select_recommendations(many)
    assert len(kept) == 5 and kept[0] is a and kept[1] is c
    reasons = [d["reason"] for d in discarded]
    assert (
        reasons.count(rule.DISCARD_DUPLICATE) == 1 and reasons.count(rule.DISCARD_OVER_LIMIT) == 3
    )


def test_no_recommendation_text_adds_excluded_count():
    assert (
        rule.no_recommendation_text("아이디어가 이미 충분히 다름", 0)
        == "아이디어가 이미 충분히 다름"
    )
    assert rule.no_recommendation_text(None, 2).endswith("검증에서 제외됨 2건")
    text = rule.no_recommendation_text('<doc id="x">근거 부족', 1)
    assert "<doc" not in text and "근거 부족" in text  # 구획 태그 무력화


def test_apply_recommendation_fills_title_goal_and_direction_as_a_preview():
    rec = make("가제 A", "요약 A", "차별점 A")
    new_req, preview = rule.apply_recommendation(REQ, rec, 0)
    assert new_req.title_hint == "가제 A" and new_req.differentiation == "차별점 A"
    assert new_req.goal.startswith(REQ.goal) and new_req.goal.endswith("(추천 과제 보완) 요약 A")
    assert preview.changed == ["title_hint", "goal", "differentiation"] and preview.index == 0
    assert new_req.current_state == REQ.current_state  # 다른 칸은 그대로
    again, p2 = rule.apply_recommendation(
        new_req, rec, 0
    )  # 두 번 적용해도 보완 문구가 겹치지 않는다
    assert again.goal == new_req.goal and p2.changed == []


def test_self_overlap_is_relative_to_the_original_idea():
    from rra.domain.models import OverlapAlert

    def a(doc, sim, blocking=True):
        return OverlapAlert(doc_id=doc, title="t", tier="own", similarity=sim, blocking=blocking)

    original = [a("own:1", 0.88), a("own:2", 0.5, blocking=False)]
    assert not rule.self_overlaps(original, [])  # 차단 없음 → 통과
    assert not rule.self_overlaps(original, [a("own:1", 0.85)])  # 같은 문서, 더 멀어짐
    assert rule.self_overlaps(original, [a("own:1", 0.88)])  # 같은 문서, 그대로
    assert rule.self_overlaps(original, [a("own:1", 0.9)])  # 더 가까워짐
    assert rule.self_overlaps(original, [a("own:2", 0.9)])  # 원래 차단 아니던 문서 → 새 중복
    assert rule.self_overlaps(original, [a("own:1", 0.86)], margin=0.03)  # 여유 폭 미달

    assert rule.self_overlap_docs(original, [a("own:1", 0.9), a("own:2", 0.9)]) == [
        "own:1",
        "own:2",
    ]
