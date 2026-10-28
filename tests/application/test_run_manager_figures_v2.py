"""[G] RunManager 그림 v2 — 초안 뒤 기본 세트(As-Is/To-Be + 기법 추천 0~2, 최대 4장),
추천 카드 동작([넣기 확정]·[필요 없음]·[다시 넣기]·[다른 기법으로 바꾸기])이 새 버전·변경 n건이
되는지,
제출 전 점검의 결정 전 추천, [다시 추천], 마무리, 공용 계정 internal 제외."""

import json

import pytest

from rra.application.services import RunManager
from rra.application.services.run_manager import EditRejected
from rra.application.usecases.figures import FigureConfig, MakeFigures
from rra.application.usecases.generate_proposal import GenerateProposal
from rra.domain.models import Document
from rra.domain.rules import figures as figure_rules
from rra.domain.rules.lint import ChoiceSpec, LintRules
from tests.fakes import (
    FakeFigureRenderer,
    FakeImageGenerator,
    FakeLLM,
    FakePromptLibrary,
    FakeRenderer,
    FakeRunLog,
    FakeSlot,
    FakeTaskRunner,
    InMemoryRepository,
    InMemoryRunStore,
)
from tests.figure_v2_helpers import CATALOG, REQ, SECTIONS, SNAP, RoutingLLM, picks

USER = "local"
KEYS = [*(s.key for s in SECTIONS), "task_type", "utilization"]


def _answers():
    out = [
        json.dumps(
            [{"text": s.text, "evidence": list(s.evidence)} for s in sec.sentences],
            ensure_ascii=False,
        )
        for sec in SECTIONS
    ]
    out.append(
        json.dumps({"choices": ["applied"], "sentences": [{"text": "응용 사유", "evidence": []}]})
    )
    out.append(
        json.dumps(
            {"choices": ["software"], "sentences": [{"text": "프로그램 제공", "evidence": []}]}
        )
    )
    return out


@pytest.fixture
def repo():
    r = InMemoryRepository()
    r.seed(
        [
            Document(
                doc_id="alio:1", source="alio", doc_type="internal_report", title="궤도", body="b"
            ),
            Document(
                doc_id="own:9",
                source="own",
                doc_type="internal_report",
                title="내부",
                body="b",
                visibility="internal",
            ),
        ],
        list(SNAP.chunks),
    )
    return r


def make_manager(repo, argon=None, renderer=None):
    rules = LintRules(
        sections=KEYS,
        required_sections=KEYS[:3],
        titles={k: k for k in KEYS},
        choices={
            "task_type": ChoiceSpec(options="task_types"),
            "utilization": ChoiceSpec(options="utilization", max=10),
        },
    )
    gen = GenerateProposal(FakeLLM(_answers()), repo, FakePromptLibrary(), rules, KEYS)
    argon = argon or RoutingLLM(picks=picks("swot", "cost_benefit"))
    figures = MakeFigures(
        RoutingLLM(),
        FakePromptLibrary(),
        FakeFigureRenderer(),
        images=FakeImageGenerator(),
        argon=argon,
        argon_model="gemini-4-argon",
        config=FigureConfig(max_default=4),
        titles=rules.titles,
        clock=lambda: "2026-10-28T10:00:00+00:00",
        catalog=CATALOG,
    )
    return RunManager(
        gen,
        InMemoryRunStore(),
        FakeSlot(),
        FakeRunLog(),
        FakeTaskRunner(),
        clock=lambda: "2026-10-28T10:00:00+00:00",
        renderer=renderer or FakeRenderer(),
        figures=figures,
    )


async def _run(mgr, **kw):
    state = await mgr.wait(USER, (await mgr.submit(USER, REQ, **kw)).run_id)
    assert state.status == "drafted", state.status
    return state


def _by_kind(figures):
    return {getattr(f.spec, "technique", f.kind): f for f in figures}


async def test_default_set_is_as_is_to_be_plus_recommended_techniques(repo):
    mgr = make_manager(repo)
    state = await _run(mgr)
    v1 = mgr.store.load_version(USER, state.run_id, 1)
    kinds = sorted(f.kind for f in v1.figures)
    assert kinds == ["as_is_to_be", "technique", "technique"] and len(v1.figures) <= 4
    assert not {"concept", "process", "roadmap"} & set(kinds)
    by = _by_kind(v1.figures)
    assert by["as_is_to_be"].section == "objective" and by["as_is_to_be"].recommendation is None
    assert by["swot"].recommendation.status == "pending" and by["swot"].included
    assert state.figure_techniques["status"] == "recommended"
    assert sorted(state.figure_techniques["picks"]) == ["cost_benefit", "swot"]
    check = {i.key: i for i in (await mgr.submit_check(USER, state.run_id)).items}
    assert check["figures_undecided"].count == 2 and not check["figures_undecided"].ok
    assert "넣기 확정" in check["figures_undecided"].detail


async def test_recommendation_decisions_are_marks_and_swap_makes_a_version(repo):
    mgr = make_manager(repo)
    state = await _run(mgr)
    rid = state.run_id
    figs = _by_kind(mgr.store.load_version(USER, rid, 1).figures)
    swot, cb = figs["swot"].id, figs["cost_benefit"].id
    # 항목 21: 넣기 확정·필요 없음·다시 넣기는 상태 표시 — 버전 번호 그대로
    v2 = await mgr.figure_action(USER, rid, swot, "accept", base_version=1)
    assert v2.version == 1 and mgr.store.list_versions(USER, rid) == [1]
    assert _by_kind(v2.figures)["swot"].recommendation.status == "accepted"
    v1 = mgr.store.load_version(USER, rid, 1)  # 버전 파일은 그대로
    assert [r["change"] for r in figure_rules.figure_diff(v1.figures, v2.figures)] == ["accepted"]
    v3 = await mgr.figure_action(USER, rid, cb, "dismiss", base_version=1)
    dismissed = _by_kind(v3.figures)["cost_benefit"]
    assert dismissed.included is False and dismissed.recommendation.status == "dismissed"
    check = {i.key: i for i in (await mgr.submit_check(USER, rid)).items}
    assert check["figures_undecided"].ok and check["figures_undecided"].count == 0
    v4 = await mgr.figure_action(USER, rid, cb, "include")  # 추천 그림의 [넣기] = 다시 넣기
    restored = _by_kind(v4.figures)["cost_benefit"]
    assert restored.included and restored.recommendation.status == "accepted"
    assert v4.version == 1
    kinds = [m.kind for m in mgr.store.load_marks(USER, rid, 1).log]
    assert kinds == ["figure_accept", "figure_dismiss", "figure_restore"]
    changes = await mgr.changes(USER, rid)
    assert changes.total == 0 and changes.confirmations >= 2  # "변경 0건 · 확인 n건"
    # 다른 기법으로 바꾸기 — 같은 자리·id, 다시 결정 전, 바뀐 기법 기록
    v5 = await mgr.figure_action(USER, rid, swot, "swap", technique="pugh")
    swapped = next(f for f in v5.figures if f.id == swot)
    assert swapped.spec.technique == "pugh" and swapped.section == "tech_importance"
    assert (
        swapped.recommendation.status == "pending" and swapped.recommendation.swapped_from == "swot"
    )
    assert v5.version == 2 and v5.note.startswith("분석 기법 바꾸기 — 분석 기법 그림 – ")
    assert [r["change"] for r in figure_rules.figure_diff(v4.figures, v5.figures)] == ["swapped"]
    with pytest.raises(EditRejected):
        await mgr.figure_action(USER, rid, swot, "swap", technique="magic")
    with pytest.raises(EditRejected, match="해당 없음"):
        await mgr.figure_action(USER, rid, swot, "swap", technique="lcc")  # 분석 skip
    as_is = _by_kind(v5.figures)["as_is_to_be"].id
    with pytest.raises(EditRejected):
        await mgr.figure_action(USER, rid, as_is, "accept")  # 추천 그림이 아님
    assert len(await mgr.versions(USER, rid)) == 2


async def test_retry_recommendation_respects_slots_and_reports_empty_result(repo):
    argon = RoutingLLM(picks=picks("swot", "cost_benefit"))
    mgr = make_manager(repo, argon=argon)
    state = await _run(mgr)
    rid = state.run_id
    with pytest.raises(EditRejected, match="이미 2장"):
        await mgr.retry_techniques(USER, rid)
    cb = _by_kind(mgr.store.load_version(USER, rid, 1).figures)["cost_benefit"].id
    await mgr.figure_action(USER, rid, cb, "dismiss")
    # 이미 있는 기법은 빼고 고른다 → 같은 답이면 고를 것이 없다 (해당 없음, 버전 없음)
    version, outcome = await mgr.retry_techniques(USER, rid)
    assert version is None and outcome.status == "none"
    assert (await mgr.figure_techniques(USER, rid))["status"] == "none"
    assert '"technique": "swot"' not in argon.prompts_for("[분석 기법 추천]")[-1]
    argon.picks = picks("pugh")
    version, outcome = await mgr.retry_techniques(USER, rid)
    assert outcome.status == "recommended" and version.note == "분석 기법 추천"
    new = _by_kind(version.figures)["pugh"]
    assert new.recommendation.status == "pending" and new.id == "f:method:t1"


async def test_add_technique_figure_and_finalize_puts_undecided_in_and_dismissed_out(repo):
    renderer = FakeRenderer()
    mgr = make_manager(repo, renderer=renderer)
    state = await _run(mgr)
    rid = state.run_id
    v = await mgr.add_figure(USER, rid, "technique", "", technique="pugh")
    added = _by_kind(v.figures)["pugh"]
    assert added.recommendation is None and added.section == "method" and v.note == "그림 추가"
    with pytest.raises(EditRejected):
        await mgr.add_figure(USER, rid, "technique", "method", technique="")
    cb = _by_kind(v.figures)["cost_benefit"].id
    await mgr.figure_action(USER, rid, cb, "dismiss")
    result = await mgr.finalize(
        USER, rid, choices={"task_type": ["applied"], "utilization": ["software"]}
    )
    assert result.state.status == "finalized"
    sent = renderer.calls[-1]["figures"]
    swot = _by_kind(v.figures)["swot"].id
    assert swot in sent and cb not in sent  # 결정 전 추천은 그대로 들어가고, 뺀 추천은 빠진다


async def test_public_account_run_excludes_internal_from_technique_prompts(repo):
    argon = RoutingLLM(picks=picks("swot"))
    mgr = make_manager(repo, argon=argon)
    await _run(mgr, scope="public")
    assert argon.prompts_for("[분석 기법 추천]")
    for prompt in argon.calls:
        if prompt.startswith("[분석 기법"):
            assert "X-9" not in prompt
    # 사내 계정 run 은 같은 근거를 본다 (검색 집합에 internal 청크가 있다는 확인)
    argon_all = RoutingLLM(picks=picks("swot"))
    await _run(make_manager(repo, argon=argon_all))
    assert any("X-9" in p for p in argon_all.prompts_for("[분석 기법 추천]"))


async def test_technique_failure_does_not_block_default_figures(repo):
    mgr = make_manager(repo, argon=RoutingLLM(fail=True))
    mgr.figures.llm = RoutingLLM(fail=True, specs={})  # 로컬도 실패
    state = await _run(mgr)
    assert state.figure_techniques["status"] == "failed"
    assert state.step("figures").status == "done"
