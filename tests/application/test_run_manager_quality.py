"""[Q] RunManager 파이프라인 — Q2 설계도 단계, Q3 섹션별 검색, Q6 정리 → v1·앱이 찾은 문제,
Q7 두 후보 → 1차 검토 선택, Q5 체크리스트·추가 문장 자동 반영, manifest. 가짜 LLM·저장소만."""

import json

from rra.application.services import RunManager
from rra.application.usecases.generate_proposal import GenerateProposal
from rra.application.usecases.outline import OutlineSections
from rra.application.usecases.review_draft import ReviewDraft
from rra.domain.models import Chunk, Document, PipelineConfig, ProposalRequest
from tests.application.test_review_manager import KEYS, _rules
from tests.fakes import (
    FakeLLM,
    FakePromptLibrary,
    FakeRenderer,
    FakeRunLog,
    FakeSlot,
    FakeTaskRunner,
    InMemoryRepository,
    InMemoryRunStore,
)

REQ = ProposalRequest(
    current_state="궤도 틀림",
    root_cause="노반",
    limitation="임계치",
    goal="예측",
    constraints="연구기간 1년 이내",
)
OUTLINE = json.dumps(
    {"sections": {"method": {"message": "이력 분석으로 예측", "evidence": ["openalex:W1#0"]}}},
    ensure_ascii=False,
)
ANSWERS = [
    '[{"text": "궤도 틀림 예측 연구", "evidence": []}]',
    '{"choices": ["applied"], "sentences": [{"text": "응용임.", "evidence": []}]}',
    # method 후보 A — 서술형 종결·연차 불일치(제약 1년)
    '[{"text": "이력을 분석한다.", "evidence": ["openalex:W1#0"]}, '
    '{"text": "2차년도 검증을 한다.", "evidence": []}]',
    # method 후보 B
    '[{"text": "열화 모형을 먼저 만듦.", "evidence": ["openalex:W1#0"]}]',
    '{"choices": ["software"], "sentences": [{"text": "프로그램 제공.", "evidence": []}]}',
]
CHECKLISTS = {"method": ["단계", "검증 방법"]}


def reply(choice="A", **extra):
    return json.dumps(
        {
            "sentences": [
                {
                    "sentence_id": "s:method:0",
                    "issue_type": "문장",
                    "comment": "구체화",
                    "revised_text": "이력을 분석해 우선순위를 정함.",
                    "evidence": ["openalex:W1#0"],
                }
            ],
            "additions": [
                {
                    "section": "method",
                    "after": "s:method:1",
                    "text": "현장 검증으로 확인함.",
                    "evidence": ["openalex:W1#0"],
                    "comment": "검증 방법 보완",
                },
                {"section": "method", "after": None, "text": "42% 개선함.", "evidence": []},
                {"section": "task_type", "text": "선택형엔 못 넣음."},
                {"section": "method", "text": "2차년도 검증을 함."},  # 이미 있는 문장
            ],
            "checklist": {
                "method": {"단계": True, "검증 방법": False, "기타": True},
                "title": {"a": True},
            },
            "candidates": {"method": {"choice": choice, "reason": f"{choice} 가 낫다"}},
            "scores": [{"criterion": "필요성", "score": 3, "reason": "r"}],
            **extra,
        },
        ensure_ascii=False,
    )


def build(*, review=None, pipeline=None, outline_answers=None, answers=None):
    repo = InMemoryRepository()
    repo.seed(
        [
            Document(
                doc_id="openalex:W1", source="openalex", doc_type="paper", title="t", abstract="a"
            )
        ],
        [
            Chunk(
                chunk_id="openalex:W1#0",
                doc_id="openalex:W1",
                ordinal=0,
                text="궤도 틀림 이력 분석",
            )
        ],
    )
    rules = _rules()
    pipeline = pipeline or PipelineConfig(
        outline=True, section_search=True, two_candidates=True, additions=True
    )
    gen = GenerateProposal(
        FakeLLM(list(answers or ANSWERS)),
        repo,
        FakePromptLibrary(),
        rules,
        KEYS,
        section_search=pipeline.section_search,
        rule_check=pipeline.rule_check,
    )
    reviewer = None
    if review is not None:
        reviewer = ReviewDraft(
            FakeLLM([review]),
            FakePromptLibrary(),
            rules,
            provider="gemini",
            model="argon",
            checklists=CHECKLISTS,
            additions=pipeline.additions,
        )
    outliner = OutlineSections(
        FakeLLM(list(outline_answers or [OUTLINE])), FakePromptLibrary(), KEYS, rules.titles
    )
    store, log = InMemoryRunStore(), FakeRunLog()
    mgr = RunManager(
        gen,
        store,
        FakeSlot(),
        log,
        FakeTaskRunner(),
        clock=lambda: "2026-10-27T00:00:00+00:00",
        renderer=FakeRenderer(),
        reviewer=reviewer,
        pipeline=pipeline,
        outliner=outliner,
    )
    return mgr, store, log


async def run(mgr):
    st = await mgr.submit("local", REQ)
    return await mgr.wait("local", st.run_id)


async def test_full_quality_pipeline_choice_a_applies_revision_and_additions():
    mgr, store, log = build(review=reply("A"))
    st = await run(mgr)
    rid = st.run_id
    assert st.status == "drafted" and st.draft_version == 2
    # Q2 설계도 단계 — outline.json 저장, 섹션 프롬프트에 설계 포함
    assert st.step("outline").status == "done" and st.step("outline").sentences == 1
    assert (await mgr.load_outline("local", rid))["sections"][0]["key"] == "method"
    method_prompt = next(c for c in mgr.generate.llm.calls if "[섹션: method]" in c)
    assert "[이 섹션의 설계" in method_prompt and "이력 분석으로 예측" in method_prompt
    # Q3 섹션별 검색 — 스냅샷에 섹션 청크 기록
    assert store.load_snapshot("local", rid).section_chunks["method"] == ["openalex:W1#0"]
    # Q7 두 후보 — B 는 candidates.json 에, 초안엔 A
    assert len(mgr.generate.llm.calls) == 5 and "[후보 B 작성]" in mgr.generate.llm.calls[3]
    assert list(store.load_candidates("local", rid)) == ["method"]
    # Q6 정리 → v1: 어미 통일, 연차 불일치 경고 → 1차 검토 "앱이 찾은 문제"
    v1 = store.load_version("local", rid, 1)
    assert [s.text for s in v1.section("method").sentences] == [
        "이력을 분석함.",
        "2차년도 검증을 함.",
    ]
    assert st.step("section:method").sentences == 2
    assert any(p["code"] == "period_mismatch" for p in store.load_state("local", rid).problems) or (
        v1.alerts >= 1
    )
    assert st.step("finalize").dropped == 2  # 자동 정리한 문장 수
    review_prompt = mgr.reviewer.llm.calls[0]
    assert "[앱이 찾은 문제" in review_prompt and "2차년도" in review_prompt
    assert "[섹션별 필수 요소" in review_prompt and "[보완 작성]" in review_prompt
    assert (
        "[후보 B — 핵심 섹션의 대안]" in review_prompt and "열화 모형을 먼저 만듦." in review_prompt
    )
    # 1차 검토 결과 — 수정안 1 + 추가 문장 1 반영, 폐기 2, 선택형 추가는 무시
    rnd = store.load_review("local", rid, 1)
    assert rnd.checklist == {"method": {"단계": True, "검증 방법": False}}
    assert rnd.checklist_coverage == 0.5
    assert rnd.candidate_choices["method"]["choice"] == "A"
    assert rnd.candidate_choices["method"]["rejected"] == "B"
    assert rnd.candidate_choices["method"]["rejected_text"] == "열화 모형을 먼저 만듦."
    additions = [c for c in rnd.comments if c.kind == "addition"]
    assert len(additions) == 3 and additions[0].status == "resolved" and additions[0].after == 1
    assert additions[1].discard_reason == "unsupported_number"
    assert additions[2].discard_reason == "empty_or_unchanged"
    assert set(rnd.applied_ids) == {"r1-1", additions[0].id} and rnd.applied_version == 2
    v2 = store.load_version("local", rid, 2)
    method = v2.section("method").sentences
    assert [s.text for s in method] == [
        "이력을 분석해 우선순위를 정함.",
        "2차년도 검증을 함.",
        "현장 검증으로 확인함.",
    ]
    assert [s.origin for s in method] == ["argon", "llm", "argon_addition"]
    assert v2.origin == "argon" and v2.changed_sections == ["method"]
    kinds = {a.id: a.kind for a in v2.annotations}
    assert kinds[additions[1].id] == "discarded" and additions[0].id not in kinds
    # manifest — 허용목록 안의 요약값만
    t = log.records[-1][1]["review"]["transfers"][0]
    assert (
        t["additions"] == 3
        and t["candidates"] == {"method": "A"}
        and t["checklist_coverage"] == 0.5
    )


async def test_choice_b_replaces_the_section_and_retires_comments_on_candidate_a():
    mgr, store, log = build(review=reply("B"))
    st = await run(mgr)
    rid = st.run_id
    rnd = store.load_review("local", rid, 1)
    assert rnd.candidate_choices["method"] == {
        "choice": "B",
        "reason": "B 가 낫다",
        "rejected": "A",
        "rejected_text": "이력을 분석함. 2차년도 검증을 함.",
    }
    v2 = store.load_version("local", rid, 2)
    assert [s.text for s in v2.section("method").sentences] == ["열화 모형을 먼저 만듦."]
    assert v2.section("method").sentences[0].origin == "llm" and v2.origin == "argon"
    by_id = {c.id: c for c in rnd.comments}
    assert (
        by_id["r1-1"].status == "discarded" and by_id["r1-1"].discard_reason == "candidate_replaced"
    )
    assert all(c.status == "discarded" for c in rnd.comments if c.kind == "addition")
    assert rnd.applied_ids == [] and rnd.applied_version == 2
    assert not any(a.reason == "candidate_replaced" for a in v2.annotations)
    assert log.records[-1][1]["review"]["transfers"][0]["candidates"] == {"method": "B"}


async def test_two_candidates_are_not_written_without_a_reviewer_and_outline_failure_continues():
    no_b = [a for i, a in enumerate(ANSWERS) if i != 3]
    mgr, store, log = build(review=None, outline_answers=["nope", "{}"], answers=no_b)
    st = await run(mgr)
    assert st.status == "drafted" and st.draft_version == 1
    assert st.step("outline").status == "error" and st.step("outline").error == "OutlineFailed"
    assert await mgr.load_outline("local", st.run_id) is None
    assert len(mgr.generate.llm.calls) == 4 and store.load_candidates("local", st.run_id) is None
    assert st.progress[1] == 8  # retrieve·outline·4 섹션·finalize·draft_review(skipped)


async def test_disabled_quality_steps_keep_the_old_plan_and_prompts():
    no_b = [a for i, a in enumerate(ANSWERS) if i != 3]
    mgr, store, log = build(review=None, pipeline=PipelineConfig(), answers=no_b)
    st = await run(mgr)
    assert [s.name for s in st.steps][:2] == ["retrieve", "section:title"]
    assert store.load_snapshot("local", st.run_id).section_chunks == {}
    assert not any("[이 섹션의 설계" in c for c in mgr.generate.llm.calls)
    assert (
        store.load_version("local", st.run_id, 1).section("method").sentences[0].text
        == "이력을 분석함."
    )
