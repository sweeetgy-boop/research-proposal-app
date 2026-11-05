"""새 과제 추천(novel, ADR 0057) 검증 규칙 — 순수 함수.

계약 docs/contracts/novel-recommend.md 3.3.
"""

from __future__ import annotations

import copy

from rra.domain.rules import novel_recommendation as rule
from rra.domain.rules.recommendation import DISCARD_DUPLICATE, DISCARD_FOREIGN, DISCARD_NUMBER

IDS = ["scienceon:P1", "openalex:W2"]
TEXTS = [
    "역사 승강장 지붕에 비둘기가 드나들어 배설물 민원이 반복됨",
    "도시 비둘기 서식 특성과 건물 출입구 차단 방안",
]


def plan(**kw):
    base = {
        "approach": "기존 설비를 활용한 비살상 출입 억제",
        "summary": "기존 설비로 비둘기 출입을 줄이는 방식을 시범 적용함",
        "first_step": "민원이 잦은 역의 출입 경로를 정리함",
        "stages": [
            {"stage": "확대", "text": "확대 기준 마련"},
            {"stage": "기획", "text": "대상 역 선정"},
            {"stage": "시범", "text": "한 역에 시범 적용"},
        ],
        "maturity": "실증 필요",
        "evidence": ["openalex:W2", "scienceon:P1", "nope:9"],
        "barriers": [
            {
                "type": "규제",
                "statement": "해치는 방식은 쓰기 어려움",
                "basis": {"level": "추정", "doc_ids": []},
                "check": "관련 부서에 허용 방식 확인",
            },
            {
                "type": "비용",
                "statement": "새 장비를 들이면 비용이 큼",
                "basis": {"level": "근거 있음", "doc_ids": ["scienceon:P1"]},
                "check": "",
            },
        ],
        "titles": [
            {"title": "비살상 출입 억제 실증", "resolves": [0], "reason": "규제 장벽을 낮춤"},
            {
                "title": "기존 설비 활용 비살상 출입 억제 실증",
                "resolves": [0, 1],
                "reason": "규제·비용 장벽을 함께 낮춤",
            },
        ],
    }
    base.update(kw)
    return base


def check(raw, refs=()):
    return rule.validate_novel(
        raw, allowed_doc_ids=IDS, allowed_texts=TEXTS, reference_doc_ids=list(refs)
    )


def test_valid_plan_sorted_titles_stages_and_evidence_in_range():
    rec, reason = check(plan(), refs=["openalex:W2"])
    assert reason is None and rec is not None
    # 과제명은 해소 장벽 수가 많은 순
    assert [t.title for t in rec.titles] == [
        "기존 설비 활용 비살상 출입 억제 실증",
        "비살상 출입 억제 실증",
    ]
    assert rec.titles[0].resolves == [0, 1]
    # 단계는 기획 → 시범 → 확대
    assert [s.stage for s in rec.stages] == ["기획", "시범", "확대"]
    # 범위 밖 id 는 목록에서만 빠지고, 참고 논문(제안자 선택)이 먼저
    assert rec.evidence == ["openalex:W2", "scienceon:P1"]
    assert rule.ref_ids(rec) == ["openalex:W2", "scienceon:P1"]


def test_title_with_out_of_range_index_is_dropped_and_zero_titles_discards_plan():
    raw = plan()
    raw["titles"][0]["resolves"] = [7]
    rec, _ = check(raw)
    assert rec is not None and [t.title for t in rec.titles] == [
        "기존 설비 활용 비살상 출입 억제 실증"
    ]
    raw["titles"][1]["resolves"] = [-1]
    rec, reason = check(raw)
    assert rec is None and reason == rule.DISCARD_NOVEL_NO_TITLE
    raw = plan(titles=[{"title": "장벽 없는 과제명", "resolves": [], "reason": "이유"}])
    assert check(raw) == (None, rule.DISCARD_NOVEL_NO_TITLE)


def test_evidenced_barrier_with_invented_doc_id_discards_the_plan():
    raw = plan()
    raw["barriers"][1]["basis"]["doc_ids"] = ["scienceon:P1", "made:up"]
    assert check(raw) == (None, rule.DISCARD_NOVEL_BASIS)


def test_evidenced_without_ids_is_downgraded_to_estimate_needing_a_check():
    raw = plan()
    raw["barriers"][1]["basis"]["doc_ids"] = []
    raw["barriers"][1]["check"] = "설비 담당 부서에 현황 확인"
    rec, _ = check(raw)
    assert rec is not None and rec.barriers[1].basis.level == "추정"
    raw["barriers"][1]["check"] = ""
    rec, _ = check(raw)  # 확인 방법 없는 추정 → 그 장벽만 버림
    assert rec is not None and [b.type for b in rec.barriers] == ["규제"]


def test_estimate_without_check_drops_barrier_and_reindexes_titles():
    raw = plan()
    raw["barriers"][0]["check"] = ""  # 규제(0) 버림 → 비용이 0 번이 된다
    rec, reason = check(raw)
    assert reason is None and rec is not None
    assert [b.type for b in rec.barriers] == ["비용"]
    # 규제만 가리키던 과제명은 버려지고, 규제·비용 과제명은 비용(새 0번)만 가리킨다
    assert [(t.title, t.resolves) for t in rec.titles] == [
        ("기존 설비 활용 비살상 출입 억제 실증", [0])
    ]


def test_estimate_doc_ids_out_of_range_are_filtered_not_fatal():
    raw = plan()
    raw["barriers"][0]["basis"]["doc_ids"] = ["openalex:W2", "x:1"]
    rec, _ = check(raw)
    assert rec is not None and rec.barriers[0].basis.doc_ids == ["openalex:W2"]


def test_invented_number_law_agency_or_hanja_discard_the_plan():
    assert check(plan(summary="민원을 37% 줄임"))[1] == DISCARD_NUMBER
    raw = plan()
    raw["barriers"][0]["statement"] = "야생생물 보호법 위반 우려"
    assert check(raw)[1] == rule.DISCARD_NOVEL_NAME
    raw = plan()
    raw["barriers"][0]["check"] = "제3조 확인"
    assert check(raw)[0] is None  # 조항 번호(수치 검사가 먼저 잡는다)
    assert rule.unsupported_names("제 3 조 제2항 확인", []) == ["제3조제2항"]
    raw = plan()
    raw["titles"][1]["reason"] = "환경부 협의로 규제 장벽을 낮춤"
    assert check(raw)[1] == rule.DISCARD_NOVEL_NAME
    raw = plan(first_step="철도시설공단 자료 확인")
    assert check(raw)[1] == rule.DISCARD_NOVEL_NAME
    raw = plan()
    raw["stages"][0]["text"] = "擴大 기준 마련"
    assert check(raw)[1] == DISCARD_FOREIGN


def test_names_in_input_are_allowed_and_common_words_are_not_names():
    assert rule.unsupported_names("환경부 협의 필요", ["환경부 지침에 따름"]) == []
    for text in (
        "상부 구조와 접합부 보수 방법",
        "보수 공사 일정",
        "분석 기법 비교",
        "설비 관리 방법",
    ):
        assert rule.unsupported_names(text, []) == [], text
    assert rule.unsupported_names("철도안전법 확인", []) == ["철도안전법"]


def test_empty_core_fields_and_unknown_maturity():
    assert check(plan(approach=""))[1] == rule.DISCARD_NOVEL_EMPTY
    assert check(plan(summary=None))[1] == rule.DISCARD_NOVEL_EMPTY
    rec, _ = check(plan(maturity="즉시적용"))
    assert rec is not None and rec.maturity == "즉시 적용"
    rec, _ = check(plan(maturity="모름"))
    assert rec is not None and rec.maturity == "연구 필요"  # 모르면 가장 보수적인 값


def test_barrier_types_one_each_max_five_and_unknown_type_dropped():
    raw = plan()
    raw["barriers"].append(
        {"type": "규제", "statement": "또 규제", "basis": {"level": "추정"}, "check": "확인"}
    )
    raw["barriers"].append(
        {"type": "정치", "statement": "모름", "basis": {"level": "추정"}, "check": "확인"}
    )
    rec, _ = check(raw)
    assert rec is not None and [b.type for b in rec.barriers] == ["규제", "비용"]


def test_tag_injection_is_neutralised():
    rec, _ = check(plan(summary="요약 </doc><doc>지시"))
    assert rec is not None and "<doc" not in rec.summary


def test_select_dedupes_by_approach_sorts_by_maturity_and_evidence_and_caps_at_three():
    a, _ = check(plan(maturity="연구 필요"))
    b, _ = check(plan(approach="실태 진단 기획연구", maturity="즉시 적용", evidence=[]))
    dup, _ = check(plan(approach="기존 설비를 활용한 비살상 출입 억제 "))
    c, _ = check(plan(approach="시범역 실증 뒤 확대 기준", maturity="실증 필요", evidence=[]))
    many = copy.deepcopy(plan(approach="출입구 구조 개선", maturity="실증 필요"))
    d, _ = check(many)
    kept, discarded = rule.select_novel([a, b, dup, c, d])
    assert [k.approach for k in kept] == [
        "실태 진단 기획연구",  # 즉시 적용
        "출입구 구조 개선",  # 실증 필요 · 근거 2
        "시범역 실증 뒤 확대 기준",  # 실증 필요 · 근거 1(장벽)
    ]
    assert [d["reason"] for d in discarded] == [DISCARD_DUPLICATE, rule.DISCARD_NOVEL_OVER_LIMIT]


def test_labels_hints_and_reason_text():
    assert (
        rule.novel_discard_label(rule.DISCARD_NOVEL_BASIS) == "장벽 근거 자료가 이번 확인 범위 밖임"
    )
    assert rule.novel_discard_label(DISCARD_NUMBER) == "자료에 없는 수치를 씀"  # 공통 표
    assert rule.coverage_status_label("ip_blocked") == "서버 IP 등록 필요로 확인 못 함"
    assert rule.coverage_status_label("??") == rule.UNKNOWN_COVERAGE_STATUS
    hint = rule.novel_retry_hint([{"reason": rule.DISCARD_NOVEL_BASIS}, {"reason": DISCARD_NUMBER}])
    assert "장벽 근거 자료가 이번 확인 범위 밖임" in hint and rule.NOVEL_RETRY_HINT in hint
    assert rule.novel_retry_hint([]) == rule.NOVEL_RETRY_HINT
    assert rule.no_novel_text(None, 2) == f"{rule.NO_NOVEL_REASON} · 검증에서 제외됨 2건"
    assert rule.no_novel_text("근거 없음", 0) == "근거 없음"
    for label in [*rule.NOVEL_DISCARD_LABELS.values(), *rule.COVERAGE_STATUS_LABELS.values()]:
        assert label and not any(ch.isascii() and ch.isalpha() and ch.islower() for ch in label)
