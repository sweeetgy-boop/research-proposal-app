"""[G] MakeFigures — 명세(Argon → 로컬, 교정 1회)·검사·밑그림·Nano Banana 1회·실패면 기본 그림·
말로 고치기(명세 변경 → 밑그림 → 새로 그림, 편집 호출 없음)·동시 생성."""

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
AS_IS = {
    "as_is": [
        {"tag": "현황", "text": "궤도 틀림이 반복 발생함"},
        {"tag": "원인", "text": "다짐 효과가 오래 가지 않음"},
        {"tag": "한계", "text": "주기적 보수로는 진행 속도를 반영하지 못함"},
    ],
    "to_be": [
        {"tag": "목표", "text": "검측 이력 기반 보수 우선순위 산정"},
        {"tag": "해결 방안", "text": "검측 이력을 분석해 구간별 진행 속도를 추정함"},
        {"tag": "기대효과", "text": "이력 기반 열화 예측 기술을 확보함"},
    ],
    "solution": "궤도 틀림 진행 속도 추정",
}


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
    # v2 [4] 비율은 내용 양으로 — 줄 4개뿐인 개념도는 21:9, 밑그림도 같은 비율
    assert images.calls[0]["aspect"] == "21:9" and "- 현황" in images.calls[0]["prompt"]
    assert build.figure.alt.startswith("연구 개념도:")
    failed = await make(FakeLLM(), FakeImageGenerator(fail=True)).draw(fig)
    assert failed.figure.renderer == "baseline" and failed.figure.error == "ConnectionError"
    assert failed.figure.image_sha == failed.figure.baseline_sha and failed.figure.calls == 1
    capped = await make(FakeLLM(), FakeImageGenerator(exhausted=True)).draw(fig)
    assert capped.figure.error == "budget" and capped.figure.renderer == "baseline"
    none = await make(FakeLLM(), None).draw(fig)
    assert none.figure.error == "no_image_llm" and none.figure.calls == 0


# 지금 생성되는 개념도처럼 상자 이름이 템플릿 라벨 (repair_spec 이 자리별로 고정한다)
CONCEPT2 = {
    "boxes": [
        {**box, "label": label}
        for box, label in zip(
            CONCEPT["boxes"], ("현황", "문제(근본 원인)", "해결 방안", "기대효과"), strict=True
        )
    ]
}


def _fig(**kw):
    return Figure(
        id="f:objective:1",
        kind="concept",
        section="objective",
        spec=parse_spec("concept", CONCEPT2),
        image_sha="current-image",
        renderer="nano_banana",
        confirmed=True,
        **kw,
    )


def _edit_answer(spec=None, style="", summary=()):
    return json.dumps({"spec": spec, "style": style, "summary": list(summary)}, ensure_ascii=False)


def _changed_concept(line):
    data = json.loads(json.dumps(CONCEPT2, ensure_ascii=False))
    data["boxes"][3]["lines"] = [line]
    return data


def _baseline(spec, caption=""):
    r = FakeFigureRenderer()
    return r.png(r.svg(spec, caption=caption))


async def test_words_text_change_becomes_spec_change_then_redraw_from_new_baseline():
    """[2] 글자 변경 요청 → Argon 명세 변경 → 검사 → 새 밑그림 → generate(밑그림 참고).
    이미지 편집(edit) 호출은 쓰지 않는다."""
    new = _changed_concept("이상 구간 조기 발견")
    argon = FakeLLM(
        [_edit_answer(new, summary=["기대효과 줄 1 '보수 우선순위 산정' → '이상 구간 조기 발견'"])]
    )
    local = FakeLLM()
    images = FakeImageGenerator()
    uc = make(local, images)
    uc.argon, uc.argon_model = argon, "gemini-4-argon"
    uc.config = FigureConfig(schemas={"concept": {"title": "ConceptSpec"}})
    fig = _fig(caption="연구 개념도")
    build = await uc.edit_by_words(
        fig,
        "기대효과 첫 줄을 '이상 구간 조기 발견'으로 바꿔. 담당 홍길동 010-1234-5678",
        sections=SECTIONS,
        request=REQ,
        snapshot=SNAP,
    )
    out = build.figure
    assert out.spec.boxes[3].lines == ["이상 구간 조기 발견"] and out.confirmed is False
    assert [c["kind"] for c in images.calls] == ["generate"]  # 이미지 편집 호출은 쓰지 않는다
    assert (
        build.baseline_png
        == _baseline(out.spec, "연구 개념도")
        != _baseline(fig.spec, "연구 개념도")
    )  # 새 명세의 밑그림
    assert build.adopted == b"NB:" + build.baseline_png  # 참고 이미지 = 새 밑그림 (현재 그림 아님)
    assert out.image_sha != "current-image" and out.renderer == "nano_banana" and out.calls == 1
    assert (
        "- 이상 구간 조기 발견" in images.calls[0]["prompt"]
        and "모양 요청" not in images.calls[0]["prompt"]
    )
    change = out.last_change
    assert change.kind == "content" and change.model == "gemini-4-argon" and change.at
    assert change.summary == ["기대효과 줄 1 '보수 우선순위 산정' → '이상 구간 조기 발견'"]
    assert out.edit_requests[-1].ok and "010-1234-5678" not in out.edit_requests[-1].text
    sent = argon.calls[0]
    assert sent.startswith("[그림 수정: concept]") and "010-1234-5678" not in sent
    assert "[현재 명세]" in sent and "보수 우선순위 산정" in sent and "[현재 글자 목록]" in sent
    assert "ConceptSpec" in sent and argon.systems[0].startswith("FIGURE_EDIT:")
    assert local.calls == []  # Argon 이 됐으면 로컬은 부르지 않는다


async def test_words_summary_falls_back_to_rule_diff_when_model_gives_none():
    new = _changed_concept("이상 구간 조기 발견")
    uc = make(FakeLLM(), FakeImageGenerator())
    uc.argon = FakeLLM([_edit_answer(new)])
    build = await uc.edit_by_words(
        _fig(),
        "기대효과 첫 줄을 '이상 구간 조기 발견'으로",
        sections=SECTIONS,
        request=REQ,
        snapshot=SNAP,
    )
    assert build.figure.last_change.summary == [
        "상자 4 줄 1 '보수 우선순위 산정' → '이상 구간 조기 발견'"
    ]


async def test_words_style_only_keeps_spec_and_redraws_baseline_with_style_and_text_list():
    images = FakeImageGenerator()
    uc = make(FakeLLM(), images)
    uc.argon = FakeLLM([_edit_answer(CONCEPT2, style="상자 테두리를 조금 더 굵게")])
    fig = _fig()
    build = await uc.edit_by_words(
        fig, "상자 테두리를 조금 더 굵게", sections=SECTIONS, request=REQ, snapshot=SNAP
    )
    assert build.figure.spec.model_dump() == fig.spec.model_dump()
    assert [c["kind"] for c in images.calls] == ["generate"]
    prompt = images.calls[0]["prompt"]
    assert "모양 요청(제안자): 상자 테두리를 조금 더 굵게" in prompt
    for text in ("현황", "궤도 틀림 반복", "보수 우선순위 산정"):  # 글자 목록은 늘 함께
        assert f"- {text}" in prompt
    assert build.adopted == b"NB:" + _baseline(fig.spec)  # 밑그림에서 새로 (현재 그림 아님)
    assert build.figure.last_change.kind == "style"
    assert build.figure.last_change.summary == ["모양: 상자 테두리를 조금 더 굵게"]
    assert build.figure.confirmed is False
    # 모양만 바꾸는데 그림 호출이 실패하면 기본 그림으로 바꾸지 않고 거절
    failing = make(FakeLLM(), FakeImageGenerator(fail=True))
    failing.argon = FakeLLM([_edit_answer(None, style="테두리 굵게")])
    with pytest.raises(SpecRejected, match="ConnectionError"):
        await failing.edit_by_words(
            fig, "테두리 굵게", sections=SECTIONS, request=REQ, snapshot=SNAP
        )
    with pytest.raises(SpecRejected, match="no_image_llm"):
        none = make(FakeLLM(), None)
        none.argon = FakeLLM([_edit_answer(None, style="테두리 굵게")])
        await none.edit_by_words(fig, "테두리 굵게", sections=SECTIONS, request=REQ, snapshot=SNAP)


async def test_words_content_change_with_image_failure_adopts_new_baseline():
    uc = make(FakeLLM(), FakeImageGenerator(exhausted=True))
    uc.argon = FakeLLM([_edit_answer(_changed_concept("이상 구간 조기 발견"))])
    build = await uc.edit_by_words(
        _fig(),
        "기대효과 첫 줄을 '이상 구간 조기 발견'으로",
        sections=SECTIONS,
        request=REQ,
        snapshot=SNAP,
    )
    assert build.figure.renderer == "baseline" and build.figure.error == "budget"
    assert build.figure.spec.boxes[3].lines == ["이상 구간 조기 발견"]


async def test_words_invalid_spec_change_is_rejected_with_reason_and_no_image_call():
    bad = json.loads(json.dumps(CONCEPT2, ensure_ascii=False))
    bad["boxes"][2]["lines"] = [
        "인공지능 로봇 도입"
    ]  # 출처·요청 어디에도 없다 → 줄이 빠져 상자가 빔
    images = FakeImageGenerator()
    argon = FakeLLM([_edit_answer(bad), _edit_answer(bad)])
    local = FakeLLM([_edit_answer(bad), "not json"])
    uc = make(local, images)
    uc.argon = argon
    with pytest.raises(SpecRejected) as err:
        await uc.edit_by_words(
            _fig(), "해결 방안을 바꿔", sections=SECTIONS, request=REQ, snapshot=SNAP
        )
    assert str(err.value) == "figure_box_empty"  # 먼저 답한 Argon 의 사유
    assert len(argon.calls) == 2 and "[형식 교정" in argon.calls[1]  # 교정 재요청 1회
    assert "인공지능 로봇 도입" in argon.calls[1]  # 무엇이 근거 밖인지 알려 준다
    assert len(local.calls) == 2 and images.calls == []
    # 아무것도 바꾸지 않은 답 → no_change
    same = make(FakeLLM(["{}"]), images)
    same.argon = FakeLLM([_edit_answer(CONCEPT2), _edit_answer(None)])
    with pytest.raises(SpecRejected, match="no_change"):
        await same.edit_by_words(_fig(), "좋게 해줘", sections=SECTIONS, request=REQ, snapshot=SNAP)
    with pytest.raises(SpecRejected, match="empty_request"):
        await same.edit_by_words(_fig(), "   ", sections=SECTIONS, request=REQ, snapshot=SNAP)


async def test_words_argon_failure_falls_back_to_local_model():
    argon = FakeLLM(fail_at={0})  # 429·예산·네트워크 — 예외
    local = FakeLLM([_edit_answer(_changed_concept("이상 구간 조기 발견"))])
    uc = make(local, FakeImageGenerator())
    uc.argon, uc.local_model = argon, "qwen-7b"
    build = await uc.edit_by_words(
        _fig(),
        "기대효과 첫 줄을 '이상 구간 조기 발견'으로",
        sections=SECTIONS,
        request=REQ,
        snapshot=SNAP,
    )
    assert build.figure.last_change.model == "qwen-7b" and len(local.calls) == 1
    assert local.calls[0].startswith("[그림 수정: concept]")


async def test_spec_generation_asks_argon_first_then_local_on_failure():
    argon = FakeLLM([json.dumps(CONCEPT, ensure_ascii=False)])
    local = FakeLLM([json.dumps(CONCEPT, ensure_ascii=False)])
    uc = make(local)
    uc.argon, uc.argon_model, uc.local_model = argon, "gemini-4-argon", "qwen-7b"
    result = await uc.make_spec("concept", "objective", SECTIONS, REQ, SNAP)
    assert result.spec is not None and result.model == "gemini-4-argon" and not result.fallback
    assert len(argon.calls) == 1 and local.calls == []
    assert argon.calls[0].startswith("[그림 명세: concept]")
    # Argon 예외(예산·429) → 로컬
    uc.argon = FakeLLM(fail_at={0})
    result = await uc.make_spec("concept", "objective", SECTIONS, REQ, SNAP)
    assert result.spec is not None and result.model == "qwen-7b" and result.fallback
    # Argon 이 교정 뒤에도 형식 오류 → 로컬
    uc.argon = FakeLLM(["{}", "{}"])
    local.responses = [json.dumps(CONCEPT, ensure_ascii=False)]
    result = await uc.make_spec("concept", "objective", SECTIONS, REQ, SNAP)
    assert result.model == "qwen-7b" and result.retries == 1 and result.calls == 3
    # 그림 기록에 명세를 쓴 모델이 남는다
    uc.argon = FakeLLM([json.dumps(CONCEPT, ensure_ascii=False)])
    builds, _ = await uc.build_all([("concept", "objective")], SECTIONS, REQ, SNAP)
    assert builds[0].figure.spec_model == "gemini-4-argon"


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
    # v2 기본 계획은 As-Is/To-Be + 일정표 — 개념도·체계도는 [다른 그림 추가]로만 (직접 계획)
    assert uc.plan(SECTIONS, REQ, SNAP) == [("as_is_to_be", "objective"), ("schedule", "method")]
    plan = [("concept", "objective"), ("process", "method"), ("schedule", "method")]
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


async def test_build_default_v2_never_fills_with_concept_process_or_roadmap():
    # 계획 as_is_to_be·schedule — schedule 이 두 번 다 형식 오류여도 개념도·로드맵으로 채우지 않는다
    llm = FakeLLM([json.dumps(AS_IS, ensure_ascii=False), "{}", "{}", "{}"])
    uc = make(llm, FakeImageGenerator())
    builds, skipped = await uc.build_default(SECTIONS, REQ, SNAP)
    assert [b.figure.kind for b in builds] == ["as_is_to_be"]
    assert builds[0].figure.section == "objective"
    assert skipped == [{"kind": "schedule", "section": "method", "reason": "schema"}]
    assert len(llm.calls) == 3  # As-Is/To-Be 1 + 일정표 1 + 교정 1
