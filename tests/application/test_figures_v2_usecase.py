"""[G] 그림 v2 유스케이스 — As-Is/To-Be 명세·비율, 분석 기법 추천(고르기 0~2 → 분석 → 그림),
해당 없음·호출 실패·규칙에 걸러짐 사유, Argon 실패 → 로컬, 공용 계정 internal 제외, 기법 바꾸기."""

from rra.application.usecases.figures import FigureConfig, MakeFigures
from rra.domain.models.figure import NEED_CALC, PRELIM_NOTE
from tests.fakes import FakeFigureRenderer, FakeImageGenerator, FakePromptLibrary
from tests.figure_v2_helpers import (
    AS_IS,
    CATALOG,
    REQ,
    SECTIONS,
    SNAP,
    RoutingLLM,
    js,
    picks,
)

TITLES = {
    "tech_importance": "2-가-(2) 기술적 중요도",
    "objective": "2-나 연구목적",
    "method": "2-다 연구 방법 및 주요내용",
    "expected_management": "3-가 기대효과 (경영혁신 측면)",
}


def make(local, *, argon=None, images=None, include_internal=True, **cfg):
    renderer = FakeFigureRenderer()
    uc = MakeFigures(
        local,
        FakePromptLibrary(),
        renderer,
        images=images if images is not None else FakeImageGenerator(),
        argon=argon,
        argon_model="gemini-4-argon",
        config=FigureConfig(**cfg),
        include_internal=include_internal,
        titles=TITLES,
        clock=lambda: "2026-10-28T10:00:00+00:00",
        catalog=CATALOG,
    )
    return uc, renderer


async def test_as_is_to_be_spec_from_input_and_draft_with_auto_aspect():
    local = RoutingLLM()
    uc, renderer = make(local)
    builds, skipped = await uc.build_default(SECTIONS, REQ, SNAP)
    kinds = [b.figure.kind for b in builds]
    assert kinds == ["as_is_to_be"] and skipped[0]["kind"] == "schedule"  # 일정 명세는 없음
    fig = builds[0].figure
    assert fig.section == "objective" and fig.spec.solution == AS_IS["solution"]
    assert renderer.aspects[0] == "16:9"  # 내용 양으로 고른 비율이 밑그림에도
    prompt = uc.images.calls[0]["prompt"]
    assert uc.images.calls[0]["aspect"] == "16:9" and "새로 디자인" in prompt
    assert "- 궤도 틀림이 반복 발생함" in prompt
    spec_prompt = local.prompts_for("[그림 명세: as_is_to_be]")[0]
    assert "[제안 입력]" in spec_prompt and "[초안]" in spec_prompt


async def test_as_is_to_be_with_text_outside_sources_is_dropped():
    bad = {**AS_IS, "solution": "드론 자율 비행 점검"}
    uc, _ = make(RoutingLLM(specs={"as_is_to_be": bad}))
    result = await uc.make_spec("as_is_to_be", "objective", SECTIONS, REQ, SNAP)
    assert result.spec is None and result.reason == "figure_text_not_in_sources"


async def test_recommend_two_techniques_analyses_and_draws_with_badge():
    argon = RoutingLLM(picks=picks("swot", "cost_benefit"))
    local = RoutingLLM()
    uc, _ = make(local, argon=argon)
    builds, outcome = await uc.recommend_techniques(SECTIONS, REQ, SNAP, slots=2)
    assert outcome.status == "recommended" and sorted(outcome.picks) == ["cost_benefit", "swot"]
    by = {b.figure.spec.technique: b.figure for b in builds}
    swot, cb = by["swot"], by["cost_benefit"]
    assert swot.id == "f:tech_importance:t1" and swot.section == "tech_importance"
    assert cb.section == "expected_management" and cb.kind == "technique"
    for f in (swot, cb):
        assert f.recommendation.status == "pending" and f.recommendation.model == "gemini-4-argon"
        assert f.recommendation.reason.endswith("맞음") and f.spec.note == PRELIM_NOTE
        assert f.spec_model == "gemini-4-argon" and f.renderer == "nano_banana" and f.undecided
    assert {it.amount for g in cb.spec.groups for it in g.items} >= {NEED_CALC, "1,200억 원"}
    assert local.calls == []  # Argon 이 답했으면 로컬은 부르지 않는다
    pick_prompt = argon.prompts_for("[분석 기법 추천]")[0]
    assert "0~2개" in pick_prompt and '"technique": "swot"' in pick_prompt
    assert '"id": "s:method:0"' in pick_prompt and "input:goal" in pick_prompt
    tech_prompt = argon.prompts_for("[분석 기법: cost_benefit]")[0]
    assert "산출 필요" in tech_prompt and "source" in tech_prompt
    image_prompts = [c["prompt"] for c in uc.images.calls]
    assert any("SWOT 분석" in p and "가로 한 줄에 나란히" in p for p in image_prompts)


async def test_slots_limit_picks_and_zero_slots_skip_without_calls():
    argon = RoutingLLM(picks=picks("swot", "pugh"))
    uc, _ = make(RoutingLLM(), argon=argon)
    builds, outcome = await uc.recommend_techniques(SECTIONS, REQ, SNAP, slots=1)
    assert len(builds) == 1 and outcome.dropped == ["pugh"]
    assert "0~1개" in argon.prompts_for("[분석 기법 추천]")[0]
    argon.calls.clear()
    builds, outcome = await uc.recommend_techniques(SECTIONS, REQ, SNAP, slots=0)
    assert builds == [] and outcome.status == "off" and argon.calls == []


async def test_no_fit_is_reported_as_none_with_reason():
    argon = RoutingLLM(picks={"picks": [], "none_reason": "비교할 대안이 본문에 없음"})
    uc, _ = make(RoutingLLM(), argon=argon)
    builds, outcome = await uc.recommend_techniques(SECTIONS, REQ, SNAP)
    assert builds == [] and outcome.status == "none"
    assert outcome.reason == "비교할 대안이 본문에 없음" and uc.images.calls == []


async def test_argon_failure_falls_back_to_local_model():
    local = RoutingLLM(picks=picks("pugh"))
    uc, _ = make(local, argon=RoutingLLM(fail=True))
    builds, outcome = await uc.recommend_techniques(SECTIONS, REQ, SNAP)
    assert outcome.status == "recommended" and outcome.model == "local"
    fig = builds[0].figure
    assert fig.spec_model == "local" and fig.recommendation.model == "local"
    assert fig.spec.rows[1].cells == ["0", "−"]


async def test_all_calls_failing_is_reported_as_failed():
    uc, _ = make(RoutingLLM(fail=True), argon=RoutingLLM(fail=True))
    builds, outcome = await uc.recommend_techniques(SECTIONS, REQ, SNAP)
    assert builds == [] and outcome.status == "failed" and outcome.reason == "ConnectionError"


async def test_analysis_rejected_by_rules_is_reported_as_filtered():
    invented = {
        "groups": [
            {"name": n, "items": [{"text": "드론 자율 비행", "rating": "상", "source": "x"}]}
            for n in ("강점", "약점", "기회", "위협")
        ]
    }
    argon = RoutingLLM(picks=picks("swot"), techniques={"swot": invented})
    local = RoutingLLM(picks=picks("swot"), techniques={"swot": invented})
    uc, _ = make(local, argon=argon)
    builds, outcome = await uc.recommend_techniques(SECTIONS, REQ, SNAP)
    assert builds == [] and outcome.status == "filtered" and outcome.dropped == ["swot"]
    # 교정 재요청 1회씩 (Argon 2 + 로컬 2)
    assert len(argon.prompts_for("[분석 기법: swot]")) == 2
    assert "[형식 교정" in argon.prompts_for("[분석 기법: swot]")[1]


async def test_model_skip_answer_means_no_figure_for_that_technique():
    argon = RoutingLLM(picks=picks("lcc"))  # lcc 답 없음 → skip
    uc, _ = make(RoutingLLM(), argon=argon)
    builds, outcome = await uc.recommend_techniques(SECTIONS, REQ, SNAP)
    assert builds == [] and outcome.status == "filtered" and outcome.reason == "skip"


async def test_public_account_run_excludes_internal_evidence():
    leaked = {
        "groups": [
            {
                "name": "비용",
                "items": [
                    {"text": "비공개 노선 X-9 보수 계획", "amount": NEED_CALC, "source": "own:9#0"}
                ],
            },
            {"name": "편익", "items": [{"text": "유지보수 비용을 절감함", "amount": NEED_CALC}]},
        ]
    }
    argon = RoutingLLM(picks=picks("cost_benefit"), techniques={"cost_benefit": leaked})
    uc, _ = make(RoutingLLM(), argon=argon)
    builds, outcome = await uc.recommend_techniques(SECTIONS, REQ, SNAP, include_internal=False)
    for prompt in argon.calls:
        assert "X-9" not in prompt  # 프롬프트에 internal 근거가 없다
    # internal 글자는 출처가 아니다 → Argon 답은 걸러지고(교정 1회 포함) 로컬 답(공개 근거)이 쓰인다
    assert len(argon.prompts_for("[분석 기법: cost_benefit]")) == 2
    texts = [it.text for g in builds[0].figure.spec.groups for it in g.items]
    assert "비공개 노선 X-9 보수 계획" not in texts and builds[0].figure.spec_model == "local"
    assert outcome.status == "recommended"
    # 사내 계정은 internal 근거를 본다
    argon2 = RoutingLLM(picks=picks("cost_benefit"), techniques={"cost_benefit": leaked})
    uc2, _ = make(RoutingLLM(), argon=argon2)
    await uc2.recommend_techniques(SECTIONS, REQ, SNAP)
    assert "X-9" in argon2.prompts_for("[분석 기법 추천]")[0]


async def test_build_technique_for_swap_keeps_id_and_section():
    uc, _ = make(RoutingLLM(), argon=RoutingLLM())
    build, reason = await uc.build_technique(
        "pugh", "tech_importance", SECTIONS, REQ, SNAP, figure_id="f:tech_importance:t1"
    )
    assert reason is None and build.figure.id == "f:tech_importance:t1"
    assert build.figure.section == "tech_importance" and build.figure.recommendation is None
    none, why = await uc.build_technique("lcc", None, SECTIONS, REQ, SNAP)
    assert none is None and why == "skip"
    rows = uc.technique_catalog_rows()
    assert len(rows) == 20 and {"key", "label", "family_label", "summary", "fits"} <= set(rows[0])


async def test_pick_answer_with_bad_shape_is_corrected_once():
    argon = RoutingLLM(picks='{"picks": "swot"}')
    local = RoutingLLM(picks=js(picks("swot")))
    uc, _ = make(local, argon=argon)
    builds, outcome = await uc.recommend_techniques(SECTIONS, REQ, SNAP)
    assert len(argon.prompts_for("[분석 기법 추천]")) == 2  # 교정 1회
    assert outcome.status == "recommended" and outcome.model == "local"
