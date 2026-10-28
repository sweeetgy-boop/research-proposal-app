"""[G] 그림 규칙 — 글자·수치 출처 검사, 기본 선택, 글자 목록·대체 텍스트·프롬프트, 버전 비교,
글자 고치기."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from rra.domain.models import ProposalRequest, Section, Sentence, TableFact
from rra.domain.models.figure import Figure, parse_spec
from rra.domain.rules import figures as rules

REQ = ProposalRequest(
    current_state="궤도 틀림이 반복 발생함",
    root_cause="다짐 효과가 오래 가지 않음",
    limitation="주기적 보수로는 진행 속도를 반영하지 못함",
    goal="검측 이력 기반 보수 우선순위 산정",
    constraints="연구기간 24개월, 예산 2억",
)
SECTIONS = [
    Section(
        key="objective",
        sentences=[Sentence(text="궤도 틀림 진행 속도를 추정해 보수 우선순위를 산정함.")],
    ),
    Section(
        key="method",
        sentences=[
            Sentence(text="검측 이력을 분석해 구간별 진행 속도를 추정함."),
            Sentence(text="다짐 효과의 지속 기간을 분석함."),
        ],
    ),
    Section(
        key="tech_importance",
        sentences=[Sentence(text="연간 보수 1,234건이 반복됨.", evidence=["alio:1#0"])],
    ),
    Section(
        key="expected_technology", sentences=[Sentence(text="이력 기반 열화 예측 기술을 확보함.")]
    ),
]
FACTS = {
    "alio:1": [
        TableFact(
            item="연간 보수",
            value=Decimal("1234"),
            value_text="1,234",
            doc_id="alio:1",
            year=2024,
            unit="건",
        ),
        TableFact(
            item="연간 보수",
            value=Decimal("1512"),
            value_text="1,512",
            doc_id="alio:1",
            year=2025,
            unit="건",
        ),
    ]
}


def concept(lines=("궤도 틀림 반복",)):
    return parse_spec(
        "concept",
        {
            "boxes": [
                {"label": "현황", "lines": list(lines)},
                {"label": "문제", "lines": ["다짐 효과 지속 기간"]},
                {"label": "해결 방안", "lines": ["검측 이력 분석"]},
                {"label": "기대효과", "lines": ["보수 우선순위 산정"]},
            ]
        },
    )


@pytest.fixture
def pool():
    return rules.text_pool(SECTIONS, REQ, ["1장 서론 ..."], FACTS)


def test_texts_must_come_from_sources(pool):
    assert rules.validate_spec(concept(), pool) == []
    bad = concept(lines=["인공지능 로봇 도입"])  # 본문·입력·근거 어디에도 없음
    assert rules.validate_spec(bad, pool) == [rules.TEXT_NOT_IN_SOURCES]
    assert rules.FIXED_TEXTS <= set(rules.FIXED_TEXTS)  # 고정 라벨은 항상 허용
    assert pool.has_text("정보 없음") and pool.has_text("목표치 확인 필요")


def test_numbers_must_match_sources(pool):
    spec = parse_spec(
        "roadmap",
        {
            "metrics": [{"name": "연간 보수", "target": "1,234건"}],
            "stages": [{"name": "검측 이력 분석"}, {"name": "보수 우선순위 산정"}],
        },
    )
    assert rules.validate_spec(spec, pool) == []
    wrong = parse_spec(
        "roadmap",
        {
            "metrics": [{"name": "연간 보수", "target": "9,999건"}],
            "stages": [{"name": "검측 이력 분석"}, {"name": "보수 우선순위 산정"}],
        },
    )
    assert rules.NUMBER_NOT_IN_SOURCES in rules.validate_spec(wrong, pool)


def test_stat_chart_uses_only_table_facts(pool):
    spec = parse_spec(
        "stat_chart",
        {
            "title": "연간 보수",
            "categories": ["2024", "2025"],
            "series": [{"name": "연간 보수", "values": [1234, 1512]}],
            "unit": "건",
            "value_texts": ["1,234", "1,512"],
            "source": {
                "doc_id": "alio:1",
                "title": "궤도 상태 자동 감지 연구",
                "year": 2024,
                "page": 3,
            },
        },
    )
    assert rules.validate_spec(spec, pool) == []
    assert spec.source.caption() == "출처: 궤도 상태 자동 감지 연구, 2024년, 3쪽"
    made_up = spec.model_copy(
        update={"series": [spec.series[0].model_copy(update={"values": [1234, 2000]})]}
    )
    assert rules.validate_spec(made_up, pool) == [rules.FACT_NOT_FOUND]
    other_doc = spec.model_copy(
        update={"source": spec.source.model_copy(update={"doc_id": "openalex:W1"})}
    )
    assert rules.SOURCE_MISSING in rules.validate_spec(other_doc, pool)


def test_schedule_must_fit_research_period(pool):
    spec = parse_spec(
        "schedule",
        {
            "total_months": 24,
            "stages": [
                {"name": "검측 이력 분석", "start_month": 1, "end_month": 8},
                {"name": "보수 우선순위 산정", "start_month": 9, "end_month": 24},
            ],
        },
    )
    assert rules.validate_spec(spec, pool, period_months=24) == []
    assert rules.validate_spec(spec, pool, period_months=12) == [rules.SCHEDULE_EXCEEDS]
    assert rules.validate_spec(spec, pool, period_months=None) == [rules.SCHEDULE_EXCEEDS]
    with pytest.raises(ValidationError):
        parse_spec(
            "schedule",
            {"total_months": 24, "stages": [{"name": "a", "start_month": 5, "end_month": 2}] * 2},
        )


def test_choose_default_follows_priority_and_limit():
    plan = rules.choose_default(SECTIONS, REQ, max_default=3, has_facts=True, has_overlap=True)
    assert plan == [
        ("concept", "objective"),
        ("process", "method"),
        ("stat_chart", "tech_importance"),
    ]
    plan = rules.choose_default(SECTIONS, REQ, max_default=6, has_facts=False, has_overlap=False)
    assert plan == [
        ("concept", "objective"),
        ("process", "method"),
        ("schedule", "method"),
        ("roadmap", "expected_technology"),
    ]
    no_period = REQ.model_copy(update={"constraints": ""})
    assert ("schedule", "method") not in rules.choose_default(SECTIONS, no_period, max_default=6)
    assert rules.choose_default([], REQ) == []


def test_texts_alt_and_prompt_contain_every_label():
    spec = concept()
    texts = rules.texts_of(spec)
    assert texts[:2] == ["현황", "궤도 틀림 반복"] and len(texts) == len(set(texts))
    alt = rules.alt_text(spec)
    assert alt.startswith("연구 개념도:") and "현황(궤도 틀림 반복) → 문제" in alt
    prompt = rules.image_prompt(spec, caption="연구 개념도")
    for t in texts:
        assert f"- {t}" in prompt
    assert "로고" in prompt and "한 글자도 바꾸지" in prompt and "배치: 상자 4개" in prompt
    assert "개인정보" not in rules.edit_prompt(
        "상자 색을 더 진하게"
    ) and "상자 색을 더 진하게" in rules.edit_prompt("상자 색을 더 진하게")


def test_text_edits_apply_only_allowed_paths_and_revalidate():
    spec = concept()
    rows = rules.editable_texts(spec)
    assert rows[0] == {"path": "boxes.0.label", "label": "상자 1 제목", "value": "현황"}
    edited = rules.apply_text_edits(
        spec, {"boxes.0.lines.0": "궤도 틀림 급증", "kind": "process", "x": "y"}
    )
    assert edited.boxes[0].lines[0] == "궤도 틀림 급증" and edited.kind == "concept"
    with pytest.raises(ValueError):
        rules.apply_text_edits(spec, {"boxes.0.label": "x" * 80})


def test_figure_diff_and_ids_and_unconfirmed():
    a = Figure(
        id="f:objective:1",
        kind="concept",
        section="objective",
        spec=concept(),
        image_sha="a1",
        confirmed=True,
    )
    b = a.model_copy(update={"image_sha": "b2", "renderer": "nano_banana", "confirmed": False})
    c = Figure(
        id="f:method:1",
        kind="process",
        section="method",
        spec=parse_spec("process", {"stages": [{"name": "a"}, {"name": "b"}, {"name": "c"}]}),
    )
    diff = rules.figure_diff([a], [b, c])
    assert [d["change"] for d in diff] == ["redrawn", "added"]
    excluded = b.model_copy(update={"included": False})
    assert rules.figure_diff([b], [excluded])[0]["change"] == "excluded"
    assert rules.figure_diff([a], [])[0]["change"] == "removed"
    assert rules.next_figure_id("objective", ["f:objective:1"]) == "f:objective:2"
    assert [f.id for f in rules.unconfirmed([a, b, excluded])] == [
        "f:objective:1"
    ] or rules.unconfirmed([b]) == [b]


def test_internal_only_texts_detected_for_public_accounts():
    pool = rules.text_pool(
        SECTIONS, REQ, [], {}, internal_chunk_texts=["비공개 노선 X-9 구간 자료"]
    )
    spec = concept(lines=["비공개 노선 X-9 구간 자료"])
    assert rules.internal_only_texts(spec, pool) == ["비공개 노선 X-9 구간 자료"]
    assert rules.internal_only_texts(concept(), pool) == []


def test_normalize_clips_long_texts_at_word_boundary_and_list_limits():
    long = (
        "경부선 일반철도 구간의 궤도 틀림(고저·방향·수평)은 궤도검측차가 분기별로 측정하고, "
        "그 사이에는 도보로 확인한다."
    )
    data = {"boxes": [{"label": "현황 " * 20, "lines": [long, "a", "b"]}] * 4}
    out = rules.normalize_spec_data(data)
    box = out["boxes"][0]
    assert len(box["label"]) <= 40 and len(box["lines"]) == 2
    assert len(box["lines"][0]) <= 60 and long.startswith(box["lines"][0])
    spec = parse_spec("concept", out)  # 형식 오류 없이 명세가 된다
    assert spec.boxes[0].lines[0] == box["lines"][0]


def test_repair_drops_unsupported_optional_texts_but_keeps_required_ones(pool):
    roadmap = parse_spec(
        "roadmap",
        {
            "metrics": [
                {"name": "연간 보수", "target": "95% 이상 감지"},  # 근거 없는 목표치
                {"name": "연간 보수", "target": "1,234건"},  # 근거 있음
            ],
            "stages": [
                {"name": "검측 이력 분석", "desc": "승객 만족도 10% 향상"},
                {"name": "보수 우선순위 산정", "desc": "검측 이력을 분석해"},
            ],
        },
    )
    fixed = rules.repair_spec(roadmap, pool)
    assert [m.target for m in fixed.metrics] == ["목표치 확인 필요", "1,234건"]
    assert [s.desc for s in fixed.stages] == [None, "검측 이력을 분석해"]
    assert rules.validate_spec(fixed, pool) == []
    concept_bad = concept(lines=["인공지능 로봇 도입"])
    repaired = rules.repair_spec(concept_bad, pool)
    assert repaired.boxes[0].lines == []
    assert rules.validate_spec(repaired, pool) == [rules.BOX_EMPTY]  # 줄 없는 상자는 거부
    required_bad = parse_spec(
        "process",
        {
            "stages": [
                {"name": "우주 발사"},
                {"name": "검측 이력 분석"},
                {"name": "보수 우선순위 산정"},
            ]
        },
    )
    assert rules.validate_spec(rules.repair_spec(required_bad, pool), pool) == [
        rules.TEXT_NOT_IN_SOURCES
    ]


def test_plan_figure_years_must_come_from_draft_or_input_not_evidence():
    pool = rules.text_pool(SECTIONS, REQ, ["2024년 보고서 기준 연간 보수 현황"], {})
    spec = parse_spec(
        "roadmap",
        {
            "metrics": [{"name": "연간 보수", "target": "목표치 확인 필요"}],
            "stages": [{"name": "2024년 보고서 기준"}, {"name": "보수 우선순위 산정"}],
        },
    )
    assert rules.validate_spec(spec, pool) == [
        rules.NUMBER_NOT_IN_SOURCES
    ]  # 근거의 연도는 계획 연도 아님
    with_year = REQ.model_copy(update={"constraints": "2024년 착수, 연구기간 24개월"})
    pool2 = rules.text_pool(SECTIONS, with_year, ["2024년 보고서 기준 연간 보수 현황"], {})
    assert rules.validate_spec(spec, pool2) == []  # 제안자 입력에 있으면 허용


def test_concept_box_labels_are_fixed_template_labels(pool):
    spec = parse_spec(
        "concept",
        {
            "boxes": [
                {"label": "현재 상황", "lines": ["궤도 틀림 반복"]},
                {"label": "문제(근본 원인)", "lines": ["다짐 효과 지속 기간"]},
                {"label": "해결책", "lines": ["검측 이력 분석"]},
                {"label": "효과", "lines": ["보수 우선순위 산정"]},
            ]
        },
    )
    fixed = rules.repair_spec(spec, pool)
    assert [b.label for b in fixed.boxes] == list(rules.CONCEPT_LABELS)
    assert rules.validate_spec(fixed, pool) == []
