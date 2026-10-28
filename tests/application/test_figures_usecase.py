"""[G] MakeFigures — 명세(교정 1회·대체)·검사·밑그림·Nano Banana 1회·실패면 기본 그림·말로 고치기·
동시 생성."""

import json

import pytest

from rra.application.usecases.figures import FigureConfig, MakeFigures, SpecRejected
from rra.domain.models import Chunk, ProposalRequest, RetrievalSnapshot, Section, Sentence
from rra.domain.models.figure import Figure, parse_spec
from tests.fakes import FakeFigureRenderer, FakeImageGenerator, FakeLLM, FakePromptLibrary

REQ = ProposalRequest(
    current_state="궤도 틀림이 반복 발생함",
    root_cause="다짐 효과가 오래 가지 않음",
    limitation="주기적 보수로는 진행 속도를 반영하지 못함",
    goal="검측 이력 기반 보수 우선순위 산정",
    constraints="연구기간 24개월",
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
        key="expected_technology", sentences=[Sentence(text="이력 기반 열화 예측 기술을 확보함.")]
    ),
]
SNAP = RetrievalSnapshot(
    query_hash="q",
    chunks=[Chunk(chunk_id="alio:1#0", doc_id="alio:1", ordinal=0, text="1장 서론 ...")],
)
CONCEPT = {
    "boxes": [
        {"label": "현황", "lines": ["궤도 틀림 반복"]},
        {"label": "문제", "lines": ["다짐 효과 지속 기간"]},
        {"label": "해결 방안", "lines": ["검측 이력 분석"]},
        {"label": "기대효과", "lines": ["보수 우선순위 산정"]},
    ]
}
PROCESS = {
    "stages": [
        {"name": "검측 이력 분석", "outputs": ["구간별 진행 속도"]},
        {"name": "다짐 효과 분석"},
        {"name": "보수 우선순위 산정"},
    ]
}
BAD = {"boxes": [{"label": "현황", "lines": ["인공지능 로봇 도입"]}] * 4}


def make(llm, images=None, fallback=None, **cfg):
    return MakeFigures(
        llm,
        FakePromptLibrary(),
        FakeFigureRenderer(),
        images=images,
        fallback_llm=fallback,
        config=FigureConfig(max_default=3, aspects={"schedule": "21:9"}, **cfg),
        titles={"objective": "2-나 연구목적"},
        clock=lambda: "2026-10-28T10:00:00+00:00",
    )


async def test_spec_prompt_carries_schema_draft_input_and_is_validated():
    llm = FakeLLM([json.dumps(CONCEPT, ensure_ascii=False)])
    uc = make(llm)
    uc.config = FigureConfig(schemas={"concept": {"title": "ConceptSpec"}})
    result = await uc.make_spec("concept", "objective", SECTIONS, REQ, SNAP)
    assert result.spec is not None and result.spec.kind == "concept" and result.calls == 1
    prompt = llm.calls[0]
    assert (
        prompt.startswith("[그림 명세: concept]")
        and "[스키마" in prompt
        and "ConceptSpec" in prompt
    )
    assert "[초안]" in prompt and "[제안 입력]" in prompt and '<doc id="alio:1#0">' in prompt
    assert llm.systems[0].startswith("FIGURES:")


async def test_bad_spec_is_corrected_once_then_fallback_then_dropped():
    local = FakeLLM([json.dumps(BAD, ensure_ascii=False), "not json"])
    remote = FakeLLM([json.dumps(CONCEPT, ensure_ascii=False)])
    result = await make(local, fallback=remote).make_spec(
        "concept", "objective", SECTIONS, REQ, SNAP
    )
    assert result.spec is not None and result.retries == 1 and result.fallback and result.calls == 3
    assert "[형식 교정" in local.calls[1] and "인공지능 로봇 도입" in local.calls[1]
    # 대체도 실패하면 명세 없음 — 사유 코드만
    result = await make(FakeLLM(["{}", "{}"]), fallback=FakeLLM(["[]"])).make_spec(
        "concept", "objective", SECTIONS, REQ, SNAP
    )
    assert result.spec is None and result.reason in ("schema", "json")


async def test_skip_when_no_period_or_no_facts_and_model_skip_answer():
    uc = make(FakeLLM([json.dumps({"skip": "no_period"})]))
    no_period = REQ.model_copy(update={"constraints": ""})
    assert (
        await uc.make_spec("schedule", "method", SECTIONS, no_period, SNAP)
    ).reason == "no_period"
    assert (
        await uc.make_spec("stat_chart", "tech_importance", SECTIONS, REQ, SNAP)
    ).reason == "no_facts"
    result = await uc.make_spec("schedule", "method", SECTIONS, REQ, SNAP)
    assert result.spec is None and result.reason == "skip" and result.retries == 0


async def test_draw_uses_nano_banana_once_and_falls_back_to_baseline_on_failure():
    fig = Figure(
        id="f:objective:1", kind="concept", section="objective", spec=parse_spec("concept", CONCEPT)
    )
    images = FakeImageGenerator()
    build = await make(FakeLLM(), images).draw(fig)
    assert build.figure.renderer == "nano_banana" and build.figure.model == "fake/nano-banana"
    assert (
        build.figure.calls == 1
        and build.adopted.startswith(b"NB:")
        and build.adopted_mime == "image/jpeg"
    )
    assert build.figure.image_sha != build.figure.baseline_sha and build.figure.confirmed is False
    assert images.calls[0]["aspect"] == "16:9" and "- 현황" in images.calls[0]["prompt"]
    assert build.figure.alt.startswith("연구 개념도:")
    failed = await make(FakeLLM(), FakeImageGenerator(fail=True)).draw(fig)
    assert failed.figure.renderer == "baseline" and failed.figure.error == "ConnectionError"
    assert failed.figure.image_sha == failed.figure.baseline_sha and failed.figure.calls == 1
    capped = await make(FakeLLM(), FakeImageGenerator(exhausted=True)).draw(fig)
    assert capped.figure.error == "budget" and capped.figure.renderer == "baseline"
    none = await make(FakeLLM(), None).draw(fig)
    assert none.figure.error == "no_image_llm" and none.figure.calls == 0


async def test_edit_by_words_strips_personal_data_and_records_request():
    fig = Figure(
        id="f:objective:1",
        kind="concept",
        section="objective",
        spec=parse_spec("concept", CONCEPT),
        image_sha="x",
    )
    images = FakeImageGenerator()
    build = await make(FakeLLM(), images).edit_by_words(
        fig, b"IMG", "image/png", "화살표를 굵게. 담당 홍길동 010-1234-5678"
    )
    assert (
        build.adopted == b"EDIT:IMG" and build.figure.calls == 1 and build.figure.confirmed is False
    )
    assert (
        build.figure.edit_requests[0].ok
        and "010-1234-5678" not in build.figure.edit_requests[0].text
    )
    assert (
        "010-1234-5678" not in images.calls[0]["prompt"]
        and "화살표를 굵게" in images.calls[0]["prompt"]
    )
    assert "- 궤도 틀림 반복" in images.calls[0]["prompt"]  # 명세 글자 목록을 함께 보낸다
    with pytest.raises(SpecRejected):
        await make(FakeLLM(), FakeImageGenerator(exhausted=True)).edit_by_words(
            fig, b"IMG", "image/png", "x"
        )
    with pytest.raises(SpecRejected):
        await make(FakeLLM(), None).edit_by_words(fig, b"IMG", "image/png", "x")


async def test_build_all_plans_and_numbers_figures_and_shrinks_large_images():
    answers = [
        json.dumps(CONCEPT, ensure_ascii=False),
        json.dumps(PROCESS, ensure_ascii=False),
        "{}",
        "{}",
    ]
    llm = FakeLLM(answers)
    images = FakeImageGenerator()
    uc = make(llm, images, max_bytes=4)
    uc.shrink = lambda data, mime: (data[:4], "image/jpeg")
    plan = uc.plan(SECTIONS, REQ, SNAP)
    assert plan == [("concept", "objective"), ("process", "method"), ("schedule", "method")]
    builds, skipped = await uc.build_all(plan, SECTIONS, REQ, SNAP)
    assert [b.figure.id for b in builds] == ["f:method:1", "f:objective:1"]
    assert {b.figure.kind for b in builds} == {"concept", "process"}
    assert skipped == [{"kind": "schedule", "section": "method", "reason": "schema"}]
    assert all(len(b.adopted) == 4 for b in builds)  # 상한 축소
    assert len(images.calls) == 2


async def test_public_account_drops_internal_only_texts():
    snap = RetrievalSnapshot(
        query_hash="q",
        chunks=[
            Chunk(
                chunk_id="own:9#0",
                doc_id="own:9",
                ordinal=0,
                text="비공개 노선 X-9 자료",
                visibility="internal",
            )
        ],
    )
    spec = {
        **CONCEPT,
        "boxes": [{"label": "현황", "lines": ["비공개 노선 X-9 자료"]}, *CONCEPT["boxes"][1:]],
    }
    cited = [
        SECTIONS[0].model_copy(
            update={"sentences": [Sentence(text="노선 자료를 쓴다.", evidence=["own:9#0"])]}
        ),
        *SECTIONS[1:],
    ]
    uc = make(FakeLLM([json.dumps(spec, ensure_ascii=False)] * 2))
    uc.include_internal = False
    result = await uc.make_spec("concept", "objective", cited, REQ, snap)
    assert result.spec is None and result.reason == "internal_text"
    # 인용하지 않은 청크의 글자는 처음부터 출처가 아니다 (검색 집합 전체를 근거로 치지 않는다)
    uc2 = make(FakeLLM([json.dumps(spec, ensure_ascii=False)] * 2))
    result2 = await uc2.make_spec("concept", "objective", SECTIONS, REQ, snap)
    assert result2.spec is None and result2.reason == "figure_box_empty"
    assert "비공개 노선 X-9 자료" in uc2.llm.calls[1]  # 교정 재요청이 없는 글자를 알려 준다
    assert "X-9" not in uc.llm.calls[0]  # internal 청크는 프롬프트에도 넣지 않는다


async def test_build_default_fills_up_with_next_kind_when_one_is_rejected():
    roadmap = {
        "metrics": [{"name": "열화 예측 기술 확보", "target": "목표치 확인 필요"}],
        "stages": [{"name": "검측 이력 분석"}, {"name": "보수 우선순위 산정"}],
    }
    # 계획 concept·process·schedule — schedule 이 두 번 다 형식 오류 → roadmap 으로 채운다
    llm = FakeLLM(
        [
            json.dumps(CONCEPT, ensure_ascii=False),
            json.dumps(PROCESS, ensure_ascii=False),
            "{}",
            "{}",
            json.dumps(roadmap, ensure_ascii=False),
        ]
    )
    uc = make(llm, FakeImageGenerator())
    builds, skipped = await uc.build_default(SECTIONS, REQ, SNAP)
    assert sorted(b.figure.kind for b in builds) == ["concept", "process", "roadmap"]
    assert skipped == [{"kind": "schedule", "section": "method", "reason": "schema"}]
