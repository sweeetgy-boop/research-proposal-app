"""그림 칸 글자 — 명세 프롬프트의 칸별 상한, 끊긴 구절 거절 → 교정 재요청 → 온전한 낱말 묶음,
기법 분석·말로 고치기도 같은 규칙, 다시 그리기 1회 (2026-10-29, ADR 0044)."""

import copy
from pathlib import Path

import yaml

from rra.application.usecases.figures import FigureConfig, MakeFigures
from rra.domain.models.figure import Figure, parse_spec
from rra.domain.rules import figure_phrases as phrases
from rra.domain.rules import figures as rules
from tests.fakes import FakeFigureRenderer, FakeLLM, FakePromptLibrary
from tests.figure_v2_helpers import AS_IS, CATALOG, REQ, SECTIONS, SNAP, SWOT, RoutingLLM, js

ROOT = Path(__file__).resolve().parents[2]


def make(llm, **cfg):
    return MakeFigures(
        llm,
        FakePromptLibrary(),
        FakeFigureRenderer(),
        config=FigureConfig(**cfg),
        catalog=CATALOG,
        clock=lambda: "2026-10-29T09:00:00+00:00",
    )


def with_goal(text: str) -> dict:
    spec = copy.deepcopy(AS_IS)
    spec["to_be"][0]["text"] = text
    return spec


async def test_incomplete_phrase_is_re_asked_with_the_reason_and_the_fix_is_taken():
    cut = "검측 이력 기반 보수 우선순위를"  # 조사로 끝남 — 잘린 구절
    llm = FakeLLM([js(with_goal(cut)), js(AS_IS)])
    result = await make(llm).make_spec("as_is_to_be", "objective", SECTIONS, REQ, SNAP)
    assert result.spec is not None and result.retries == 1 and len(llm.calls) == 2
    assert "[칸 글자 수 상한]" in llm.calls[0] and "20자 안" in llm.calls[0]
    assert "끝맺지 않은 구절" in llm.calls[1] and cut in llm.calls[1]
    assert result.spec.to_be[0].text == AS_IS["to_be"][0]["text"]


async def test_still_incomplete_after_re_ask_falls_back_to_whole_words_never_a_cut():
    cut = "검측 이력 기반 보수 우선순위를"
    llm = FakeLLM([js(with_goal(cut)), js(with_goal(cut))])
    result = await make(llm).make_spec("as_is_to_be", "objective", SECTIONS, REQ, SNAP)
    assert result.spec is not None and len(llm.calls) == 2
    got = result.spec.to_be[0].text
    assert got == "검측 이력 기반 보수 우선순위"  # 끝 낱말의 조사만 던다 — 낱말은 그대로
    for t in rules.texts_of(result.spec):
        assert phrases.is_complete(t)


async def test_words_outside_sources_after_re_ask_become_in_source_whole_words():
    """명사형으로 바꾸며 새 낱말('미추정')을 만들면 교정 뒤 그 칸 글자 안의 출처 낱말 묶음으로."""
    spec = copy.deepcopy(AS_IS)
    spec["solution"] = "구간별 진행 속도 미추정"
    llm = FakeLLM([js(spec), js(spec)])
    result = await make(llm).make_spec("as_is_to_be", "objective", SECTIONS, REQ, SNAP)
    assert result.spec is not None and len(llm.calls) == 2
    assert "구간별 진행 속도 미추정" in llm.calls[1]  # 교정 재요청이 출처 밖 글자를 알려 준다
    assert result.spec.solution == "구간별 진행 속도"


async def test_over_limit_text_is_not_clipped_but_re_asked():
    long = "검측 이력 기반 보수 우선순위 산정 궤도 틀림이 반복 발생함"  # 31자 > 스키마 30자
    llm = FakeLLM([js(with_goal(long)), js(AS_IS)])
    result = await make(llm).make_spec("as_is_to_be", "objective", SECTIONS, REQ, SNAP)
    assert result.spec is not None and len(llm.calls) == 2
    assert f"20자 넘음({len(long)}자)" in llm.calls[1]
    assert result.spec.to_be[0].text == AS_IS["to_be"][0]["text"]  # 모델이 다시 쓴 답


async def test_technique_analysis_gets_limits_and_never_clips_items():
    long_item = "검측 이력 자료를 오랫동안 축적해 왔음"  # 20자 > 16자
    swot = copy.deepcopy(SWOT)
    swot["groups"][0]["items"][0]["text"] = long_item
    llm = RoutingLLM(techniques={"swot": swot})
    uc = make(llm)
    spec, reason, _model = await uc.analyze_technique("swot", SECTIONS, REQ, SNAP)
    prompts = llm.prompts_for("[분석 기법: swot]")
    assert "[칸 글자 수 상한]" in prompts[0] and "16자 안" in prompts[0]
    assert "30자 안" not in prompts[0]
    assert len(prompts) == 2 and "16자 넘음" in prompts[1]  # 교정 재요청이 이유를 알린다
    # 같은 답이 다시 오면 온전한 낱말 묶음으로 — 앞에서부터 자르지 않는다
    if spec is not None:
        item = spec.groups[0].items[0].text
        assert len(item) <= 16 and phrases.is_complete(item)
        assert all(w in long_item.split() for w in item.split()[:-1])
    else:
        assert reason in phrases.PHRASE_CODES


async def test_words_edit_keeps_the_proposers_own_wording_but_checks_ai_text():
    uc = make(FakeLLM())
    fig = Figure(
        id="f:objective:1",
        kind="as_is_to_be",
        section="objective",
        spec=parse_spec("as_is_to_be", AS_IS),
    )
    mine = "궤도 틀림이 반복 발생하는 구간이 많음"  # 21자 — 제안자가 적은 글자는 그대로
    request = f"현황 칸을 '{mine}' 으로"
    pool = rules.with_texts(uc.pool(SECTIONS, REQ, SNAP), [*rules.texts_of(fig.spec), request])
    new = copy.deepcopy(AS_IS)
    new["as_is"][0]["text"] = mine
    uc.llm = FakeLLM([js({"spec": new, "style": "", "summary": ["현황 바꿈"]})])
    change = await uc.change_spec(fig, request, pool=pool, period=24)
    assert change.spec.as_is[0].text == mine
    # AI 가 지어 끊은 글자는 교정 재요청 뒤 온전한 낱말 묶음
    cut = copy.deepcopy(AS_IS)
    cut["as_is"][1]["text"] = "다짐 효과가 오래"  # 근거 낱말 "오래" — 끊긴 구절은 아니다
    cut["to_be"][0]["text"] = "검측 이력 기반 보수 우선순위를"
    uc.llm = FakeLLM([js({"spec": cut, "style": ""}), js({"spec": cut, "style": ""})])
    change2 = await uc.change_spec(fig, "목표 칸을 짧게", pool=pool, period=24)
    assert len(uc.llm.calls) == 2 and "끝맺지 않은 구절" in uc.llm.calls[1]
    assert change2.spec.to_be[0].text == "검측 이력 기반 보수 우선순위"


def test_max_image_redraws_is_one_and_the_truncating_level_setting_is_gone():
    assert FigureConfig().max_image_redraws == 1
    fit = yaml.safe_load((ROOT / "config/figures.yaml").read_text(encoding="utf-8"))["fit"]
    assert fit["max_image_redraws"] == 1 and "max_shorten" not in fit
    assert not hasattr(FigureConfig(), "max_shorten")
