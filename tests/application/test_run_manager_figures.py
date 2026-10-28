"""[G] RunManager — 그림 단계(v1 에 그림), 검토 입력·그림 의견, 카드 동작(새 버전·되돌리기),
제출 점검, 마무리 삽입·manifest. FakeLLM·가짜 이미지 생성기만."""

import json

import pytest

from rra.adapters.logging.file_run_log import check_manifest
from rra.application.services import RunManager
from rra.application.services.run_manager import EditRejected, VersionConflict, manifest
from rra.application.usecases.figures import FigureConfig, MakeFigures
from rra.application.usecases.generate_proposal import GenerateProposal
from rra.application.usecases.review_draft import ReviewDraft
from rra.domain.models import Chunk, Document, ProposalRequest
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

USER = "local"
KEYS = ["objective", "method", "expected_technology", "task_type", "utilization"]
REQ = ProposalRequest(
    current_state="궤도 틀림이 반복 발생함",
    root_cause="다짐 효과가 오래 가지 않음",
    limitation="주기적 보수로는 진행 속도를 반영하지 못함",
    goal="검측 이력 기반 보수 우선순위 산정",
)
CONCEPT = {
    "boxes": [
        {"label": "현황", "lines": ["궤도 틀림 반복"]},
        {"label": "문제", "lines": ["다짐 효과"]},
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
ROADMAP = {
    "metrics": [{"name": "열화 예측 기술 확보", "target": "목표치 확인 필요"}],
    "stages": [{"name": "검측 이력 분석"}, {"name": "보수 우선순위 산정"}],
}


def js(text, ev=()):
    return json.dumps([{"text": text, "evidence": list(ev)}], ensure_ascii=False)


SECTION_ANSWERS = [
    js("궤도 틀림 진행 속도를 추정해 보수 우선순위를 산정함."),
    js("검측 이력을 분석해 구간별 진행 속도를 추정함."),
    js("이력 기반 열화 예측 기술을 확보함."),
    json.dumps({"choices": ["applied"], "sentences": [{"text": "응용 사유", "evidence": []}]}),
    json.dumps({"choices": ["software"], "sentences": [{"text": "프로그램 제공", "evidence": []}]}),
]


@pytest.fixture
def repo():
    r = InMemoryRepository()
    r.seed(
        [
            Document(
                doc_id="alio:1",
                source="alio",
                doc_type="internal_report",
                title="궤도",
                body="본문",
            )
        ],
        [Chunk(chunk_id="alio:1#0", doc_id="alio:1", ordinal=0, text="1장 서론")],
    )
    return r


def make_manager(repo, *, spec_answers=None, images=None, review=None, renderer=None):
    rules = LintRules(
        sections=KEYS,
        required_sections=KEYS[:3],
        titles={k: k for k in KEYS},
        choices={
            "task_type": ChoiceSpec(options="task_types"),
            "utilization": ChoiceSpec(options="utilization", max=10),
        },
    )
    gen = GenerateProposal(FakeLLM(list(SECTION_ANSWERS)), repo, FakePromptLibrary(), rules, KEYS)
    answers = (
        spec_answers
        if spec_answers is not None
        else [
            json.dumps(CONCEPT, ensure_ascii=False),
            json.dumps(PROCESS, ensure_ascii=False),
            json.dumps(ROADMAP, ensure_ascii=False),
        ]
    )
    figures = MakeFigures(
        FakeLLM(answers),
        FakePromptLibrary(),
        FakeFigureRenderer(),
        images=images if images is not None else FakeImageGenerator(),
        # 예전 기본 세트로 카드 동작을 시험한다 (v2 기본 세트는 test_run_manager_figures_v2.py)
        config=FigureConfig(max_default=3, auto_kinds=("concept", "process", "roadmap")),
        titles=rules.titles,
        clock=lambda: "2026-10-28T10:00:00+00:00",
    )
    log = FakeRunLog()
    reviewer = None
    if review is not None:
        reviewer = ReviewDraft(
            FakeLLM([review]), FakePromptLibrary(), rules, provider="fake", model="r"
        )
    mgr = RunManager(
        gen,
        InMemoryRunStore(),
        FakeSlot(),
        log,
        FakeTaskRunner(),
        clock=lambda: "2026-10-28T10:00:00+00:00",
        renderer=renderer or FakeRenderer(),
        reviewer=reviewer,
        figures=figures,
    )
    return mgr, log


async def test_figures_step_attaches_figures_to_v1_and_manifest(repo):
    mgr, log = make_manager(repo)
    state = await mgr.wait(USER, (await mgr.submit(USER, REQ)).run_id)
    assert state.status == "drafted" and state.step("figures").status == "done"
    assert state.step("figures").sentences == 3 and state.step("figures").dropped == 0
    v1 = mgr.store.load_version(USER, state.run_id, 1)
    assert [f.kind for f in v1.figures] == ["roadmap", "process", "concept"]  # id(문자열) 순
    fig = v1.figures[2]
    assert fig.id == "f:objective:1" and fig.renderer == "nano_banana" and fig.confirmed is False
    assert mgr.store.load_figure_image(USER, state.run_id, fig.image_sha)[1] == "image/jpeg"
    assert mgr.store.load_figure_image(USER, state.run_id, fig.baseline_sha)[1] == "image/png"
    assert [row["id"] for row in state.figures] == [f.id for f in v1.figures]
    assert state.figures[0]["renderer"] == "nano_banana" and state.figures[0]["calls"] == 1
    m = log.records[-1][1]
    check_manifest(m)
    assert m["figures"][0]["kind"] == "roadmap" and "spec" not in m["figures"][0]
    # [23] 그림마다 본문 폭 맞춤 기록 (숫자·코드만) — 통합 점검 "그림이 본문 폭에 맞게 들어감 n/n"
    fit = m["figures"][0]["figure_fit"]
    assert fit["width_mm"] == 153.8 and fit["ratio"] in ("16:9", "21:9", "4:1")
    assert set(fit) >= {"width_mm", "height_mm", "ratio", "fits", "min_text_pt"}
    assert v1.figures[0].fit is not None
    view = await mgr.get_draft(USER, state.run_id)
    assert [f.id for f in view.figures] == [f.id for f in v1.figures]


async def test_figure_failures_fall_back_to_baseline_and_bad_specs_are_skipped(repo):
    mgr, _ = make_manager(
        repo,
        spec_answers=[json.dumps(CONCEPT, ensure_ascii=False), "{}", "{}", "{}", "{}"],
        images=FakeImageGenerator(fail=True),
    )
    state = await mgr.wait(USER, (await mgr.submit(USER, REQ)).run_id)
    v1 = mgr.store.load_version(USER, state.run_id, 1)
    assert state.status == "drafted" and len(v1.figures) == 1
    assert v1.figures[0].renderer == "baseline" and v1.figures[0].error == "ConnectionError"
    assert state.step("figures").dropped == 2  # 명세 실패 2건은 건너뜀


async def test_review_gets_figure_specs_and_mismatch_comments_become_memos(repo):
    review = json.dumps(
        {
            "sentences": [],
            "figures": [
                {"figure_id": "f:objective:1", "comment": "본문은 4단계인데 그림은 3단계"},
                {"figure_id": "f:nope:9", "comment": "없는 그림"},
            ],
        },
        ensure_ascii=False,
    )
    mgr, _ = make_manager(repo, review=review)
    state = await mgr.wait(USER, (await mgr.submit(USER, REQ)).run_id)
    assert state.status == "drafted" and state.review_rounds == 1
    sent = mgr.reviewer.llm.calls[0]
    assert (
        "[그림 명세" in sent and '"figure_id": "f:objective:1"' in sent and "궤도 틀림 반복" in sent
    )
    rnd = mgr.store.load_review(USER, state.run_id, 1)
    figs = [c for c in rnd.comments if c.kind == "figure"]
    assert (
        len(figs) == 1 and figs[0].figure_id == "f:objective:1" and figs[0].section == "objective"
    )
    check = await mgr.submit_check(USER, state.run_id)
    by = {i.key: i for i in check.items}
    assert by["figures_mismatch"].count == 1 and not by["figures_mismatch"].ok
    assert by["figures_unconfirmed"].count == 3
    assert by["figures_unconfirmed"].target == "section:expected_technology"
    current = mgr.store.load_version(USER, state.run_id, state.draft_version)
    assert len(current.figures) == 3  # v2(또는 v1 메모)에도 그림이 이어진다


async def test_card_actions_make_versions_and_restore_brings_old_figure_back(repo):
    mgr, _ = make_manager(repo)
    state = await mgr.wait(USER, (await mgr.submit(USER, REQ)).run_id)
    rid = state.run_id
    v = await mgr.figure_action(USER, rid, "f:objective:1", "confirm", base_version=1)
    assert v.version == 2 and v.origin == "edit" and v.note == "그림 confirm"
    assert next(f for f in v.figures if f.id == "f:objective:1").confirmed is True
    with pytest.raises(VersionConflict):
        await mgr.figure_action(USER, rid, "f:objective:1", "exclude", base_version=1)
    v = await mgr.figure_action(
        USER, rid, "f:objective:1", "texts", texts={"boxes.0.lines.0": "궤도 틀림 급증"}
    )
    fig = next(f for f in v.figures if f.id == "f:objective:1")
    assert (
        v.version == 3 and fig.spec.boxes[0].lines[0] == "궤도 틀림 급증" and fig.confirmed is False
    )
    assert fig.calls == 2 and "f:objective:1" in await _ids(mgr, rid, 3)
    assert fig.last_change.kind == "content"  # 글자 고치기도 "바뀐 내용"을 남긴다
    assert fig.last_change.summary == ["상자 1 줄 1 '궤도 틀림 반복' → '궤도 틀림 급증'"]
    # 말로 고치기(모양만) — 명세 그대로, 밑그림에서 새로 그림 (편집 호출 없음)
    mgr.figures.llm.responses = [
        json.dumps({"spec": None, "style": "화살표를 굵게", "summary": []}, ensure_ascii=False)
    ]
    v = await mgr.figure_action(USER, rid, "f:objective:1", "words", request_text="화살표를 굵게")
    fig = next(f for f in v.figures if f.id == "f:objective:1")
    assert v.version == 4 and fig.calls == 3 and fig.edit_requests[0].text == "화살표를 굵게"
    assert fig.last_change.kind == "style" and fig.last_change.summary == ["모양: 화살표를 굵게"]
    assert fig.spec.boxes[0].lines[0] == "궤도 틀림 급증" and fig.confirmed is False
    assert mgr.store.load_figure_image(USER, rid, fig.image_sha)[0].startswith(b"NB:")
    assert {c["kind"] for c in mgr.figures.images.calls} == {"generate"}
    v = await mgr.figure_action(USER, rid, "f:objective:1", "baseline")
    fig = next(f for f in v.figures if f.id == "f:objective:1")
    assert fig.renderer == "baseline" and fig.image_sha == fig.baseline_sha
    v = await mgr.figure_action(USER, rid, "f:objective:1", "exclude")
    assert next(f for f in v.figures if f.id == "f:objective:1").included is False
    assert len(await mgr.versions(USER, rid)) == 6  # 문장은 같아도 버전은 만들어졌다
    restored = await mgr.revert(USER, rid, 2)
    fig = next(f for f in restored.figures if f.id == "f:objective:1")
    assert fig.confirmed is True and fig.renderer == "nano_banana" and fig.included is True
    assert (
        mgr.store.load_figure_image(USER, rid, fig.image_sha) is not None
    )  # 옛 그림 파일이 남아 있다
    with pytest.raises(EditRejected):
        await mgr.figure_action(USER, rid, "f:none:1", "confirm")
    with pytest.raises(EditRejected):
        await mgr.figure_action(USER, rid, "f:objective:1", "words", request_text="  ")


async def test_add_figure_and_finalize_passes_included_figures_to_renderer(repo):
    renderer = FakeRenderer()
    mgr, log = make_manager(repo, renderer=renderer)
    state = await mgr.wait(USER, (await mgr.submit(USER, REQ)).run_id)
    rid = state.run_id
    mgr.figures.llm.responses = [json.dumps(CONCEPT, ensure_ascii=False)]
    v = await mgr.add_figure(USER, rid, "concept", "method")
    assert any(f.id == "f:method:2" for f in v.figures) and v.note == "그림 추가"
    await mgr.figure_action(USER, rid, "f:method:2", "exclude")
    result = await mgr.finalize(
        USER, rid, choices={"task_type": ["applied"], "utilization": ["software"]}
    )
    assert result.state.status == "finalized"
    assert renderer.calls[-1]["figures"] == [  # 양식의 섹션 순서 (그림 번호 = 이 순서)
        "f:objective:1",
        "f:method:1",
        "f:expected_technology:1",
    ]
    rows = {r["id"]: r for r in result.state.figures}
    assert rows["f:objective:1"]["number"] == 1 and rows["f:expected_technology:1"]["number"] == 3
    assert rows["f:expected_technology:1"]["placement"] == "inline"
    assert rows["f:expected_technology:1"]["number"] == 3
    assert rows["f:method:2"]["placement"] is None
    m = manifest(result.state, None)
    check_manifest(m)
    assert m["figures"][0]["placement"] == "inline"
    assert m["figures"][0]["figure_fit"] is not None  # 가짜 렌더러는 그림 단계 기록을 이어받는다


async def _ids(mgr, rid, version):
    return [f.id for f in (await mgr.get_version(USER, rid, version)).figures]


async def test_status_stays_running_while_figures_are_drawn(repo):
    """그림을 그리는 동안 저장된 상태는 running — drafted 로 먼저 보이면 편집이 락에 막힌다."""
    seen: list[str] = []

    class Watching(FakeImageGenerator):
        async def generate(self, prompt, reference, **kw):
            seen.append(mgr.store.load_state(USER, run_id[0]).status)
            return await super().generate(prompt, reference, **kw)

    run_id: list[str] = []
    mgr, _ = make_manager(repo, images=Watching())
    state = await mgr.submit(USER, REQ)
    run_id.append(state.run_id)
    final = await mgr.wait(USER, state.run_id)
    assert seen and set(seen) == {"running"}
    assert final.status == "drafted" and final.step("finalize").status == "done"


async def test_words_spec_change_makes_version_and_invalid_change_is_rejected(repo):
    """[2] 말로 고치기 = 명세 변경 → 밑그림 → 새로 그림. 검사 실패면 409 사유, 버전 없음."""
    mgr, _ = make_manager(repo)
    state = await mgr.wait(USER, (await mgr.submit(USER, REQ)).run_id)
    rid = state.run_id
    before = next(f for f in state_figures(mgr, rid) if f.id == "f:method:1")
    new_spec = json.loads(json.dumps(PROCESS, ensure_ascii=False))
    new_spec["stages"].insert(2, {"name": "열화 예측 모델 검증"})
    mgr.figures.llm.responses = [
        json.dumps(
            {"spec": new_spec, "style": "", "summary": ["단계 3 추가 '열화 예측 모델 검증'"]},
            ensure_ascii=False,
        )
    ]
    v = await mgr.figure_action(
        USER, rid, "f:method:1", "words", request_text="3단계로 '열화 예측 모델 검증'을 넣어"
    )
    fig = next(f for f in v.figures if f.id == "f:method:1")
    assert v.version == 2 and v.note == "그림 words" and fig.confirmed is False
    assert [s.name for s in fig.spec.stages][2] == "열화 예측 모델 검증"
    assert fig.last_change.kind == "content" and fig.last_change.summary == [
        "단계 3 추가 '열화 예측 모델 검증'"
    ]
    assert fig.baseline_sha != before.baseline_sha  # 새 명세의 밑그림
    adopted = mgr.store.load_figure_image(USER, rid, fig.image_sha)[0]
    baseline = mgr.store.load_figure_image(USER, rid, fig.baseline_sha)[0]
    assert adopted == b"NB:" + baseline  # 참고 이미지 = 새 밑그림
    assert all(c["kind"] == "generate" for c in mgr.figures.images.calls)
    # 근거에도 요청에도 없는 단계 → 거절(사유 코드 + 안내), 버전을 만들지 않는다
    bad = json.loads(json.dumps(PROCESS, ensure_ascii=False))
    bad["stages"][0]["name"] = "드론 자율 비행 점검"
    mgr.figures.llm.responses = [
        json.dumps({"spec": bad, "style": "", "summary": []}, ensure_ascii=False)
    ] * 2
    n_versions = len(await mgr.versions(USER, rid))
    n_images = len(mgr.figures.images.calls)
    with pytest.raises(EditRejected, match="없는 글자가 들어갔습니다") as rej:
        await mgr.figure_action(USER, rid, "f:method:1", "words", request_text="1단계를 바꿔")
    assert "figure_text_not_in_sources" not in str(rej.value)  # 내부 코드는 보이지 않는다
    assert len(await mgr.versions(USER, rid)) == n_versions
    assert len(mgr.figures.images.calls) == n_images  # 그림 호출도 없음
    # 이전 버전으로 가도 "바뀐 내용"은 그 버전의 그림 기록을 따른다
    v3 = await mgr.figure_action(USER, rid, "f:method:1", "confirm")
    kept = next(f for f in v3.figures if f.id == "f:method:1")
    assert kept.confirmed is True and kept.last_change.summary == fig.last_change.summary


def state_figures(mgr, rid):
    return mgr.store.load_version(USER, rid, 1).figures
