"""RunManager 흐름 ③~⑥ (ADR 0011).

로컬 작성 v1 → Argon 1차 검토 자동 반영 v2 → 직접 수정·저장·임시 저장·복원·비교 → 최종 검토 1회
(요청 시, stale 표시·다시 받기) → 마무리/다시 열기 · 동시성 · 순수 함수.
"""

import json

import pytest

from rra.application.ports import RunBusy
from rra.application.services import QueueFull, RunManager
from rra.application.services.run_manager import (
    EditRejected,
    FinalizeRejected,
    VersionConflict,
    WorkingRejected,
    apply_edit_request,
    changed_sentence_ids,
)
from rra.application.usecases.generate_proposal import GenerateProposal
from rra.application.usecases.review_draft import ReviewDraft
from rra.domain.models import (
    Chunk,
    Document,
    DraftVersion,
    PipelineConfig,
    ProposalRequest,
    ProposerInfo,
    Section,
    Sentence,
)
from rra.domain.models.proposer import Person
from rra.domain.models.review import EditRequest, SectionEdit, SentenceEdit
from rra.domain.rules.review_flow import InvalidTransition
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

KEYS = ["title", "task_type", "method", "utilization"]
RULES_KW = dict(
    template="v2026",
    sections=KEYS,
    required_sections=["title", "method"],
    number_checked=["method"],
)
ANSWERS = [
    '[{"text": "궤도 틀림 예측 연구", "evidence": []}]',
    '{"choices": ["applied"], "sentences": [{"text": "응용임.", "evidence": []}]}',
    '[{"text": "이력을 분석함.", "evidence": ["openalex:W1#0"]}, '
    '{"text": "둘째 문장임.", "evidence": []}]',
    '{"choices": ["software"], "sentences": [{"text": "프로그램 제공.", "evidence": []}]}',
]
REQ = ProposalRequest(
    current_state="궤도 틀림", root_cause="노반", limitation="임계치", goal="예측"
)
PROPOSER = ProposerInfo(
    proposer=Person(name="홍길동", rank="선임연구원", phone="042-000-0000"),
    head=Person(name="김철도", rank="처장", phone="042-000-0001"),
    department="철도연구원 기술연구처",
)


def _rules():
    from rra.domain.rules.lint import ChoiceSpec, LintRules

    return LintRules(
        **RULES_KW,
        choices={
            "task_type": ChoiceSpec(options="task_types"),
            "utilization": ChoiceSpec(options="utilization", max=10),
        },
    )


def review_reply(revised="이력을 분석해 보수 우선순위를 정함.", scores=True):
    return json.dumps(
        {
            "sentences": [
                {
                    "sentence_id": "s:method:0",
                    "issue_type": "문장",
                    "comment": "구체화",
                    "revised_text": revised,
                    "evidence": ["openalex:W1#0"],
                },
                {
                    "sentence_id": "s:method:1",
                    "issue_type": "수치",
                    "comment": "지어낸 수치",
                    "revised_text": "둘째 문장은 42% 개선임.",
                    "evidence": [],
                },  # 폐기 대상 → 메모
                {
                    "sentence_id": "s:title:0",
                    "issue_type": "문장",
                    "comment": "의견만",
                    "revised_text": None,
                },  # 수정안 없음 → 메모
            ],
            "sections": [{"section": "method", "comment": "연차별 산출물을 적을 것"}],
            "resolved": [],
            "scores": (
                [
                    {"criterion": "필요성", "score": 3, "reason": "r"},
                    {"criterion": "차별성", "score": 2, "reason": "r"},
                    {"criterion": "실현가능성", "score": 3, "reason": "r"},
                    {"criterion": "기대효과", "score": 4, "reason": "r"},
                ]
                if scores
                else []
            ),
        },
        ensure_ascii=False,
    )


def build(
    *, review_answers=None, reviewer=None, auto=True, store=None, max_queued=3, pipeline=None
):
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
    gen = GenerateProposal(FakeLLM(list(ANSWERS)), repo, FakePromptLibrary(), rules, KEYS)
    if reviewer is None and review_answers is not None:
        reviewer = ReviewDraft(
            FakeLLM(list(review_answers)),
            FakePromptLibrary(),
            rules,
            provider="gemini",
            model="argon",
        )
    store = store or InMemoryRunStore()
    log = FakeRunLog()
    mgr = RunManager(
        gen,
        store,
        FakeSlot(),
        log,
        FakeTaskRunner(),
        clock=lambda: "2026-10-27T00:00:00+00:00",
        renderer=FakeRenderer(),
        reviewer=reviewer,
        review_auto=auto,
        max_queued=max_queued,
        pipeline=pipeline,
    )
    return mgr, store, log


async def run(mgr):
    st = await mgr.submit("local", REQ)
    return await mgr.wait("local", st.run_id)


def manual(sid, text):
    return EditRequest(sentences=[SentenceEdit(sentence_id=sid, action="manual", text=text)])


# ── ③ 로컬 작성 v1 → 1차 검토 자동 반영 v2 ──────────────────
async def test_without_review_llm_the_run_is_drafted_with_v1_and_records_the_skip():
    mgr, store, log = build()
    st = await run(mgr)
    assert st.status == "drafted" and st.review_skipped and st.review_rounds == 0
    assert st.draft_review_skipped == "no_review_llm"
    assert st.draft_version == 1 and store.list_versions("local", st.run_id) == [1]
    assert st.step("draft_review").status == "skipped" and st.progress == (7, 7)
    rnd = store.load_review("local", st.run_id, 1)
    assert rnd.status == "skipped" and rnd.kind == "draft" and rnd.skipped_reason == "no_review_llm"
    manifest = log.records[-1][1]
    assert manifest["review"]["skipped"] is True and manifest["review"]["draft_review_skipped"]
    assert manifest["versions"] == [
        {
            "version": 1,
            "origin": "local",
            "changed_sections": 4,
            "sentences": 5,
            "alerts": 0,
            "open_annotations": 0,
            "decisions": 0,
        }
    ]
    # 건너뛴 뒤에는 최종 검토 없이 바로 마무리 가능(review_skipped)
    result = await mgr.finalize("local", st.run_id, proposer=PROPOSER)
    assert result.state.status == "finalized" and result.confirmation.choices["task_type"] == [
        "applied"
    ]


async def test_auto_draft_review_applies_validated_revisions_into_v2_and_keeps_the_rest_as_memos():
    mgr, store, log = build(review_answers=[review_reply()])
    st = await run(mgr)
    assert st.status == "drafted" and st.review_rounds == 1 and not st.review_skipped
    assert st.review_model == "gemini/argon" and st.draft_review_skipped is None
    assert st.step("draft_review").status == "done" and st.draft_version == 2
    rnd = store.load_review("local", st.run_id, 1)
    assert rnd.kind == "draft" and rnd.draft_version == 1 and rnd.applied_version == 2
    assert rnd.applied_ids == ["r1-1"]  # 검증 통과 수정안만 자동 반영
    assert rnd.comment("r1-1").status == "resolved"
    v1 = store.load_version("local", st.run_id, 1)
    v2 = store.load_version("local", st.run_id, 2)
    assert v1.origin == "local" and v2.origin == "argon" and v2.based_on_review == 1
    assert v2.section("method").sentences[0].text == "이력을 분석해 보수 우선순위를 정함."
    assert v2.section("method").sentences[0].origin == "argon"
    assert v2.section("method").sentences[1].text == "둘째 문장임."  # 폐기된 수정안은 원문 유지
    assert v2.section("task_type").choices == ["applied"]  # 선택값은 바꾸지 않는다
    assert v2.changed_sections == ["method"]
    # 수정안 없는 의견·폐기된 수정안·섹션 의견 → 문장 메모
    memos = {a.id: a for a in v2.annotations}
    assert memos["r1-2"].kind == "discarded" and memos["r1-2"].reason == "unsupported_number"
    assert memos["r1-2"].text == "지어낸 수치"  # 의견은 남고 수정안은 폐기
    assert memos["r1-3"].kind == "opinion" and memos["r1-3"].section == "title"
    assert memos["r1-4"].kind == "section" and memos["r1-4"].sentence is None
    assert v2.open_annotations == 3
    view = await mgr.get_draft("local", st.run_id)
    assert view.version == 2 and view.reviews == [1] and view.has_working is False
    transfer = log.records[-1][1]["review"]["transfers"][0]
    assert transfer["kind"] == "draft" and transfer["applied"] == 1
    assert transfer["public_doc_ids"] == ["openalex:W1"] and transfer["sentences_sent"] == 5
    assert "구체화" not in json.dumps(
        log.records, ensure_ascii=False
    )  # 의견 원문은 manifest 에 없다
    # 1차 검토는 한 번만
    with pytest.raises(InvalidTransition, match="한 번만"):
        await mgr.review("local", st.run_id)


async def test_draft_review_can_be_turned_off_in_pipeline_or_auto_and_started_manually():
    mgr, store, _ = build(review_answers=[review_reply()], auto=False)
    st = await run(mgr)
    assert st.status == "drafted" and st.draft_review_skipped == "disabled"
    assert st.review_skipped is False  # 검토 LLM 은 있다 — 최종 검토 없이 마무리할 수 없다
    assert store.load_review("local", st.run_id, 1).skipped_reason == "disabled"
    st = await mgr.review("local", st.run_id)
    assert st.status == "draft_reviewing"
    st = await mgr.wait("local", st.run_id)
    assert st.status == "drafted" and st.review_rounds == 1 and st.draft_version == 2
    off = PipelineConfig(draft_review=False)
    mgr2, store2, _ = build(review_answers=[review_reply()], pipeline=off)
    st2 = await run(mgr2)
    assert st2.status == "drafted" and "draft_review" not in [s.name for s in st2.steps]
    assert st2.progress == (6, 6) and st2.draft_version == 1


async def test_draft_review_failure_retries_once_then_keeps_v1_and_records_the_class_name():
    mgr, store, _ = build(review_answers=["JSON 아님", "JSON 아님"])
    st = await run(mgr)
    assert st.status == "drafted" and st.review_error == "ReviewParseFailed"
    assert st.review_rounds == 0 and st.draft_version == 1 and st.draft_review_skipped == "failed"
    assert st.step("draft_review").status == "error"
    assert len(mgr.reviewer.llm.calls) == 2  # 재시도 1회
    # 실패해도 v1 로 진행 — 편집·최종 검토 요청은 가능
    v2 = await mgr.apply_edits("local", st.run_id, manual("s:title:0", "고친 제목"))
    assert v2.version == 2 and v2.origin == "edit"


# ── ④ 직접 수정·저장·임시 저장·복원·비교 ─────────────────
async def test_edits_make_versions_use_only_validated_revisions_and_keep_manual_text():
    mgr, store, _ = build(review_answers=[review_reply()])
    st = await run(mgr)
    rid = st.run_id
    rnd = store.load_review("local", rid, 1)
    discarded = next(c for c in rnd.comments if c.status == "discarded")
    with pytest.raises(EditRejected, match="수정안이 없습니다"):
        await mgr.apply_edits(
            "local",
            rid,
            EditRequest(
                sentences=[
                    SentenceEdit(
                        sentence_id="s:method:1", action="use_revision", comment_id=discarded.id
                    )
                ]
            ),
        )
    v3 = await mgr.apply_edits(
        "local",
        rid,
        EditRequest(
            sentences=[
                SentenceEdit(
                    sentence_id="s:method:1",
                    action="manual",
                    text="제안자가 직접 고친 문장 99% 임.",
                ),
                SentenceEdit(sentence_id="s:method:1", action="insert_after", text="새로 쓴 문장."),
                SentenceEdit(sentence_id="s:title:0", action="keep"),
            ],
            note="1차 반영",
            base_version=2,
            done_annotations=["r1-3"],
        ),
    )
    assert v3.version == 3 and v3.origin == "edit" and v3.note == "1차 반영"
    method = v3.section("method")
    assert method.sentences[0].origin == "argon"  # v2 의 Argon 보완 문장 유지
    assert method.sentences[1].origin == "proposer_edit" and method.sentences[1].text.startswith(
        "제안자가"
    )
    assert method.sentences[1].evidence == []  # 원래 근거 유지 (원래 비어 있었다)
    assert method.sentences[2].origin == "proposer_input" and method.sentences[2].evidence == []
    assert v3.changed_sections == ["method"] and v3.alerts >= 1
    assert {a.id: a.status for a in v3.annotations}["r1-3"] == "done"  # 메모 처리됨
    assert v3.open_annotations == 2
    st = await mgr.status("local", rid)
    assert st.status == "editing" and st.draft_version == 3
    assert any(
        p["code"] == "unsupported_number" and p["section"] == "method" for p in st.problems
    )  # 알림만
    view = await mgr.get_draft("local", rid)
    assert view.sections[2].sentences[1].origin == "proposer_edit" and view.version == 3
    # 같은 내용 저장 → 새 버전 없음
    same = await mgr.apply_edits(
        "local",
        rid,
        EditRequest(
            sentences=[SentenceEdit(sentence_id="s:title:0", action="keep")], done_annotations=[]
        ),
    )
    assert same.version == 3 and store.list_versions("local", rid) == [1, 2, 3]
    # 동시 편집 보호
    with pytest.raises(VersionConflict, match="v2"):
        await mgr.apply_edits(
            "local",
            rid,
            EditRequest(
                sentences=[SentenceEdit(sentence_id="s:title:0", action="manual", text="x")],
                base_version=2,
            ),
        )
    # 섹션 전체 편집 — 같은 문장은 근거를 이어받고 새 문장은 proposer_input
    v4 = await mgr.apply_edits(
        "local",
        rid,
        EditRequest(
            sections=[
                SectionEdit(
                    section="method",
                    text="이력을 분석해 보수 우선순위를 정함. 통째로 쓴 새 문장임.",
                )
            ]
        ),
    )
    first, second = v4.section("method").sentences
    assert first.origin == "argon" and first.evidence == ["openalex:W1#0"]
    assert second.origin == "proposer_input" and second.evidence == []
    # 삭제·순서
    v5 = await mgr.apply_edits(
        "local",
        rid,
        EditRequest(
            sentences=[SentenceEdit(sentence_id="s:method:1", action="delete")],
            sections=[SectionEdit(section="title", order=["s:title:0"])],
        ),
    )
    assert [s.text for s in v5.section("method").sentences] == [
        "이력을 분석해 보수 우선순위를 정함."
    ]
    versions = await mgr.versions("local", rid)
    assert [v.version for v in versions] == [1, 2, 3, 4, 5]
    # 비교·복원
    diff = await mgr.diff("local", rid, 1, 5)
    assert [d["section"] for d in diff] == ["method"] and diff[0]["sentences"] == [2, 1]
    v6 = await mgr.revert("local", rid, 2)
    assert v6.version == 6 and v6.origin == "revert" and v6.reverted_from == 2
    assert v6.section("method").sentences[1].text == "둘째 문장임."
    assert store.list_versions("local", rid) == [1, 2, 3, 4, 5, 6]  # 복원해도 기록은 남는다
    with pytest.raises(EditRejected, match="v9"):
        await mgr.revert("local", rid, 9)
    with pytest.raises(EditRejected, match="편집이 없습니다"):
        await mgr.apply_edits("local", rid, EditRequest())
    with pytest.raises(EditRejected, match="그런 문장"):
        await mgr.apply_edits("local", rid, manual("s:method:7", "x"))


async def test_working_copy_is_not_a_version_and_blocks_final_review_and_finalize_until_saved():
    mgr, store, _ = build(review_answers=[review_reply(), review_reply("최종 수정안임.")])
    st = await run(mgr)
    rid = st.run_id
    await mgr.save_working("local", rid, {"sections": [{"key": "title", "texts": ["임시 제목"]}]})
    working = await mgr.load_working("local", rid)
    assert working["sections"][0]["texts"] == ["임시 제목"] and working["saved_at"]
    assert store.list_versions("local", rid) == [1, 2]
    assert (await mgr.get_draft("local", rid)).has_working is True
    with pytest.raises(InvalidTransition, match="임시 편집"):
        await mgr.final_review("local", rid)
    # 저장하면 임시 사본이 사라진다
    await mgr.apply_edits("local", rid, manual("s:title:0", "저장한 제목"))
    assert await mgr.load_working("local", rid) is None
    await mgr.save_working("local", rid, {"x": 1})
    await mgr.discard_working("local", rid)
    assert await mgr.load_working("local", rid) is None
    st = await mgr.final_review("local", rid)
    assert st.status == "final_reviewing"
    with pytest.raises(WorkingRejected):
        await mgr.save_working("local", rid, {"x": 1})  # 검토 중 편집 잠금
    await mgr.wait("local", rid)


# ── ⑤ 최종 검토 1회 · stale · 다시 받기 → ⑥ 마무리 · 다시 열기 ──
async def test_final_review_once_then_edit_marks_stale_and_re_review_is_optional():
    answers = [review_reply(), review_reply("최종 수정안임."), review_reply("다시 받은 수정안임.")]
    mgr, store, log = build(review_answers=answers)
    st = await run(mgr)
    rid = st.run_id
    assert st.draft_version == 2
    await mgr.apply_edits("local", rid, manual("s:method:1", "제안자가 고침."))  # v3
    with pytest.raises(FinalizeRejected, match="최종 검토"):
        await mgr.finalize("local", rid, proposer=PROPOSER)  # 검토 LLM 이 있으면 최종 검토 뒤에만
    st = await mgr.final_review("local", rid)
    assert st.status == "final_reviewing"
    with pytest.raises(EditRejected, match="검토 중"):
        await mgr.apply_edits("local", rid, manual("s:title:0", "x"))
    with pytest.raises(FinalizeRejected, match="final_reviewing"):
        await mgr.finalize("local", rid, proposer=PROPOSER)
    st = await mgr.wait("local", rid)
    assert st.status == "final_reviewed" and st.final_reviews == 1
    assert st.final_reviewed_version == 3 and st.stale_edits == 0 and not st.stale
    final = store.load_review("local", rid, 2)
    assert final.kind == "final" and final.final_round == 1 and final.draft_version == 3
    assert final.score_delta == {"필요성": 0, "차별성": 0, "실현가능성": 0, "기대효과": 0}
    assert (await mgr.get_review("local", rid, kind="final")).round == 2
    assert (await mgr.get_review("local", rid, 1, kind="final")).round == 2
    assert (await mgr.get_review("local", rid, kind="draft")).round == 1
    prompt = mgr.reviewer.llm.calls[1]
    assert "[검토 종류] 최종 검토" in prompt and "[1차 의견" in prompt
    assert "[1차 검토 뒤 제안자가 바꾼 문장]" in prompt and '"s:method:1"' in prompt
    assert "[1차 점수" in prompt
    # 최종 검토 수정안을 문장별로 반영해 저장 → 만든 경로 = 최종 검토 반영
    usable = next(c for c in final.comments if c.usable)
    v4 = await mgr.apply_edits(
        "local",
        rid,
        EditRequest(
            sentences=[
                SentenceEdit(sentence_id="s:method:0", action="use_revision", comment_id=usable.id)
            ]
        ),
    )
    assert v4.origin == "final_review" and v4.based_on_review == 2
    assert v4.section("method").sentences[0].text == "최종 수정안임."
    st = await mgr.status("local", rid)
    assert st.status == "editing" and st.stale and st.stale_edits == 2  # 수정 = 삭제 1 + 추가 1
    # stale 이어도 마무리는 허용 — 점검 맨 위에 경고
    result = await mgr.finalize(
        "local", rid, choices={"utilization": ["software", "manual"]}, proposer=PROPOSER
    )
    assert result.state.status == "finalized" and result.version == 4
    assert result.check.notes[0].startswith("최종 검토 이후 수정 2건")
    assert result.confirmation.choices == {
        "task_type": ["applied"],
        "utilization": ["software", "manual"],
    }
    body = json.loads(result.data)
    assert body["proposer"]["proposer"]["name"] == "홍길동"
    dumped = json.dumps({k: str(v) for k, v in vars(store).items()}, ensure_ascii=False)
    assert "홍길동" not in dumped and "042-000" not in dumped
    assert "홍길동" not in json.dumps(log.records, ensure_ascii=False)
    # 다시 열기 → 수정 → 원할 때 다시 받기(횟수 기록) → 새 파일
    st = await mgr.reopen("local", rid)
    assert st.status == "editing"
    await mgr.apply_edits("local", rid, manual("s:title:0", "다시 연 뒤 고친 제목"))
    st = await mgr.final_review("local", rid)
    st = await mgr.wait("local", rid)
    assert st.status == "final_reviewed" and st.final_reviews == 2 and st.stale_edits == 0
    assert store.list_reviews("local", rid) == [1, 2, 3]
    again = await mgr.finalize("local", rid, proposer=PROPOSER)
    assert again.state.status == "finalized" and again.version == 5 and again.data != result.data
    assert again.check.notes == [] or not again.check.notes[0].startswith("최종 검토 이후")
    with pytest.raises(EditRejected, match="finalized"):
        await mgr.reopen("local", rid)  # editing 에서는 reopen 불가
        await mgr.reopen("local", rid)
    manifest = log.records[-1][1]["review"]
    assert manifest["final_reviews"] == 2 and manifest["transfers"][1]["kind"] == "final"


async def test_finalize_a_chosen_older_version():
    mgr, store, _ = build()
    st = await run(mgr)
    await mgr.apply_edits("local", st.run_id, manual("s:title:0", "두 번째 버전 제목"))
    result = await mgr.finalize("local", st.run_id, proposer=PROPOSER, version=1)
    assert result.version == 1
    assert json.loads(result.data)["sections"]["title"] == "궤도 틀림 예측 연구"
    with pytest.raises(EditRejected, match="v7"):
        await mgr.finalize("local", st.run_id, proposer=PROPOSER, version=7)


async def test_review_respects_queue_limit_and_run_lock():
    mgr, store, _ = build(review_answers=[review_reply(), review_reply()], max_queued=1)
    st = await run(mgr)
    other = await mgr.submit("local", REQ)  # 다른 run 이 활성 → 최종 검토 시작 불가
    with pytest.raises(QueueFull):
        await mgr.final_review("local", st.run_id)
    await mgr.wait("local", other.run_id)
    store.claimed.add(("local", st.run_id))  # 다른 프로세스가 run 을 잡고 있다
    with pytest.raises(RunBusy):
        await mgr.final_review("local", st.run_id)


# ── 순수 함수 ─────────────────────────────────────────
def test_changed_sentence_ids_and_apply_edit_request():
    old = DraftVersion(
        version=1, sections=[Section(key="m", sentences=[Sentence(text="a"), Sentence(text="b")])]
    )
    new = DraftVersion(
        version=2,
        sections=[
            Section(key="m", sentences=[Sentence(text="a"), Sentence(text="B"), Sentence(text="c")])
        ],
    )
    assert changed_sentence_ids(old, new) == {"s:m:1", "s:m:2"}
    shorter = DraftVersion(version=3, sections=[Section(key="m", sentences=[Sentence(text="a")])])
    assert changed_sentence_ids(old, shorter) == {"s:m:1"}
    sections, used = apply_edit_request(
        old.sections,
        EditRequest(
            sentences=[
                SentenceEdit(sentence_id="s:m:0", action="manual", text="A"),
                SentenceEdit(sentence_id="s:m:1", action="delete"),
                SentenceEdit(sentence_id="s:m:0", action="insert_after", text="새 문장"),
            ]
        ),
        None,
    )
    assert used == set()
    assert [(s.text, s.origin) for s in sections[0].sentences] == [
        ("A", "proposer_edit"),
        ("새 문장", "proposer_input"),
    ]
    with pytest.raises(EditRejected, match="형식"):
        apply_edit_request(
            old.sections, EditRequest(sentences=[SentenceEdit(sentence_id="bad")]), None
        )
