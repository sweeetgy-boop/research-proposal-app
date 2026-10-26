"""RunManager 검토 흐름 — 자동 1차 검토·건너뜀·편집·버전·되돌리기·재검토·finalize/reopen·동시성."""

import json

import pytest

from rra.application.ports import RunBusy
from rra.application.services import QueueFull, RunManager
from rra.application.services.run_manager import (
    EditRejected,
    FinalizeRejected,
    apply_edit_request,
    changed_sentence_ids,
)
from rra.application.usecases.generate_proposal import GenerateProposal
from rra.application.usecases.review_draft import ReviewDraft
from rra.domain.models import (
    Chunk,
    Document,
    DraftVersion,
    ProposalRequest,
    ProposerInfo,
    Section,
    Sentence,
)
from rra.domain.models.proposer import Person
from rra.domain.models.review import EditRequest, SectionEdit, SentenceEdit
from rra.domain.rules.lint import ChoiceSpec, LintRules
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
RULES = LintRules(
    template="v2026",
    sections=KEYS,
    required_sections=["title", "method"],
    number_checked=["method"],
    choices={
        "task_type": ChoiceSpec(options="task_types"),
        "utilization": ChoiceSpec(options="utilization", max=10),
    },
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


def review_reply(revised="이력을 분석해 보수 우선순위를 정함."):
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
                },  # 폐기 대상
            ],
            "sections": [],
            "resolved": [],
        },
        ensure_ascii=False,
    )


def build(*, review_answers=None, reviewer=None, auto=True, store=None, max_queued=3):
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
    gen = GenerateProposal(FakeLLM(list(ANSWERS)), repo, FakePromptLibrary(), RULES, KEYS)
    if reviewer is None and review_answers is not None:
        reviewer = ReviewDraft(
            FakeLLM(list(review_answers)),
            FakePromptLibrary(),
            RULES,
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
        clock=lambda: "2026-10-26T00:00:00+00:00",
        renderer=FakeRenderer(),
        reviewer=reviewer,
        review_auto=auto,
        max_queued=max_queued,
    )
    return mgr, store, log


async def run(mgr):
    st = await mgr.submit("local", REQ)
    return await mgr.wait("local", st.run_id)


# ── 자동 검토·건너뜀 ─────────────────────────────────────
async def test_without_review_llm_the_run_stays_done_and_records_review_skipped():
    mgr, store, log = build()
    st = await run(mgr)
    assert st.status == "done" and st.review_skipped and st.review_rounds == 0
    assert st.draft_version == 1 and store.list_versions("local", st.run_id) == [1]
    rnd = store.load_review("local", st.run_id, 1)
    assert rnd.status == "skipped" and rnd.skipped_reason == "no_review_llm"
    manifest = log.records[-1][1]
    assert (
        manifest["review"]["skipped"] is True
        and manifest["review"]["transfers"][0]["status"] == "skipped"
    )
    # 건너뛴 뒤에는 바로 마무리 가능
    result = await mgr.finalize("local", st.run_id, proposer=PROPOSER)
    assert result.state.status == "finalized" and result.confirmation.choices["task_type"] == [
        "applied"
    ]


async def test_auto_first_review_runs_after_draft_and_validates_revisions():
    mgr, store, log = build(review_answers=[review_reply()])
    st = await run(mgr)
    assert st.status == "reviewed" and st.review_rounds == 1 and not st.review_skipped
    assert st.review_model == "gemini/argon"
    rnd = store.load_review("local", st.run_id, 1)
    assert rnd.status == "done" and rnd.draft_version == 1
    usable = [c for c in rnd.comments if c.usable]
    discarded = [c for c in rnd.comments if c.status == "discarded"]
    assert len(usable) == 1 and usable[0].section == "method" and usable[0].sentence == 0
    assert (
        discarded[0].discard_reason == "unsupported_number"
        and discarded[0].comment == "지어낸 수치"
    )
    view = await mgr.get_draft("local", st.run_id)
    assert view.review is rnd or view.review == rnd
    assert view.version == 1 and view.reviews == [1]
    transfer = log.records[-1][1]["review"]["transfers"][0]
    assert transfer["public_doc_ids"] == ["openalex:W1"] and transfer["sentences_sent"] == 5
    assert "구체화" not in json.dumps(
        log.records, ensure_ascii=False
    )  # 의견 원문은 manifest 에 없다


async def test_auto_review_can_be_turned_off_and_started_manually():
    mgr, store, _ = build(review_answers=[review_reply()], auto=False)
    st = await run(mgr)
    assert st.status == "done" and store.list_reviews("local", st.run_id) == []
    st = await mgr.review("local", st.run_id)
    assert st.status == "reviewing"
    st = await mgr.wait("local", st.run_id)
    assert st.status == "reviewed" and st.review_rounds == 1


async def test_review_failure_returns_to_previous_status_and_records_class_name():
    mgr, _, _ = build(review_answers=["JSON 아님"])
    st = await run(mgr)
    assert st.status == "done" and st.review_error == "ReviewParseFailed" and st.review_rounds == 0


# ── 편집·버전·되돌리기 ─────────────────────────────────
async def test_edits_make_versions_use_only_validated_revisions_and_keep_manual_text():
    mgr, store, _ = build(review_answers=[review_reply()])
    st = await run(mgr)
    rid = st.run_id
    rnd = store.load_review("local", rid, 1)
    usable = next(c for c in rnd.comments if c.usable)
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
    v2 = await mgr.apply_edits(
        "local",
        rid,
        EditRequest(
            sentences=[
                SentenceEdit(sentence_id="s:method:0", action="use_revision", comment_id=usable.id),
                SentenceEdit(
                    sentence_id="s:method:1",
                    action="manual",
                    text="제안자가 직접 고친 문장 99% 임.",
                ),
                SentenceEdit(sentence_id="s:title:0", action="keep"),
            ],
            note="1차 반영",
        ),
    )
    assert v2.version == 2 and v2.origin == "edit" and v2.based_on_review == 1
    method = v2.section("method")
    assert method.sentences[0].text == "이력을 분석해 보수 우선순위를 정함."
    assert method.sentences[0].origin == "reviewed" and method.sentences[0].evidence == [
        "openalex:W1#0"
    ]
    assert method.sentences[1].origin == "proposer" and method.sentences[1].text.startswith(
        "제안자가"
    )
    assert method.sentences[1].evidence == []  # 원래 근거 유지 (원래 비어 있었다)
    st = await mgr.status("local", rid)
    assert st.status == "editing" and st.draft_version == 2
    assert any(
        p["code"] == "unsupported_number" and p["section"] == "method" for p in st.problems
    )  # 알림만
    assert store.load_review("local", rid, 1).comment(usable.id).status == "resolved"
    view = await mgr.get_draft("local", rid)
    assert view.sections[2].sentences[1].origin == "proposer" and view.version == 2

    v3 = await mgr.apply_edits(
        "local",
        rid,
        EditRequest(
            sections=[
                SectionEdit(section="method", texts=["통째로 바꾼 첫 문장.", "둘째.", "셋째."])
            ]
        ),
    )
    assert [s.origin for s in v3.section("method").sentences] == ["proposer"] * 3
    assert v3.section("method").sentences[0].evidence == ["openalex:W1#0"]  # 같은 자리 근거 유지
    versions = await mgr.versions("local", rid)
    assert [v.version for v in versions] == [1, 2, 3]
    v4 = await mgr.revert("local", rid, 1)
    assert v4.version == 4 and v4.origin == "revert" and v4.reverted_from == 1
    assert v4.section("method").sentences[0].text == "이력을 분석함."
    assert store.list_versions("local", rid) == [1, 2, 3, 4]  # 되돌려도 기록은 남는다
    with pytest.raises(EditRejected, match="v9"):
        await mgr.revert("local", rid, 9)
    with pytest.raises(EditRejected, match="편집이 없습니다"):
        await mgr.apply_edits("local", rid, EditRequest())
    with pytest.raises(EditRejected, match="그런 문장"):
        await mgr.apply_edits(
            "local",
            rid,
            EditRequest(
                sentences=[SentenceEdit(sentence_id="s:method:7", action="manual", text="x")]
            ),
        )


# ── 재검토 무제한·마무리·다시 열기 ──────────────────────────
async def test_four_consecutive_re_reviews_then_finalize_reopen_and_finalize_again():
    answers = [review_reply(), *[review_reply(f"{i}차 수정안임.") for i in range(2, 6)]]
    mgr, store, log = build(review_answers=answers)
    st = await run(mgr)
    rid = st.run_id
    for n in range(2, 6):
        await mgr.apply_edits(
            "local",
            rid,
            EditRequest(
                sentences=[
                    SentenceEdit(
                        sentence_id="s:method:1", action="manual", text=f"{n}번째 직접 수정."
                    )
                ]
            ),
        )
        st = await mgr.review("local", rid)
        assert st.status == "reviewing"
        st = await mgr.wait("local", rid)
        assert st.status == "reviewed" and st.review_rounds == n
    assert store.list_reviews("local", rid) == [1, 2, 3, 4, 5]
    assert store.load_review("local", rid, 5).draft_version == 5
    result = await mgr.finalize(
        "local", rid, choices={"utilization": ["software", "manual"]}, proposer=PROPOSER
    )
    assert result.state.status == "finalized" and result.version == 5
    assert result.confirmation.choices == {
        "task_type": ["applied"],
        "utilization": ["software", "manual"],
    }
    body = json.loads(result.data)
    assert (
        body["proposer"]["proposer"]["name"] == "홍길동"
        and body["proposer"]["department"] == "철도연구원 기술연구처"
    )
    first = result.data
    # 제안자 정보는 어디에도 저장되지 않는다
    dumped = json.dumps({k: str(v) for k, v in vars(store).items()}, ensure_ascii=False)
    assert "홍길동" not in dumped and "042-000" not in dumped
    assert "홍길동" not in json.dumps(log.records, ensure_ascii=False)
    st = await mgr.reopen("local", rid)
    assert st.status == "editing"
    await mgr.apply_edits(
        "local",
        rid,
        EditRequest(
            sentences=[
                SentenceEdit(sentence_id="s:title:0", action="manual", text="다시 연 뒤 고친 제목")
            ]
        ),
    )
    again = await mgr.finalize("local", rid, proposer=PROPOSER)
    assert (
        again.state.status == "finalized" and again.version == 6 and again.data != first
    )  # 새 파일
    st = await mgr.reopen("local", rid)  # 마무리 뒤 다시 열기 → editing
    assert st.status == "editing"
    with pytest.raises(EditRejected, match="finalized"):
        await mgr.reopen("local", rid)  # editing 에서는 reopen 불가


async def test_finalize_is_refused_before_or_during_review_and_render_only_via_finalize():
    mgr, _, _ = build(review_answers=[review_reply()], auto=False)
    st = await run(mgr)
    assert st.status == "done" and not st.review_skipped
    with pytest.raises(FinalizeRejected, match="검토 1회"):
        await mgr.finalize("local", st.run_id, proposer=PROPOSER)
    await mgr.review("local", st.run_id)
    with pytest.raises(FinalizeRejected, match="reviewing"):
        await mgr.finalize("local", st.run_id, proposer=PROPOSER)
    with pytest.raises(EditRejected, match="검토 중"):
        await mgr.apply_edits(
            "local",
            st.run_id,
            EditRequest(
                sentences=[SentenceEdit(sentence_id="s:title:0", action="manual", text="x")]
            ),
        )
    with pytest.raises(InvalidTransition):
        await mgr.review("local", st.run_id)  # 검토 중 재검토 불가
    await mgr.wait("local", st.run_id)
    result = await mgr.finalize("local", st.run_id, proposer=PROPOSER)
    assert result.state.status == "finalized"


async def test_review_respects_queue_limit_and_run_lock():
    mgr, store, _ = build(review_answers=[review_reply()], auto=False, max_queued=1)
    st = await run(mgr)
    other = await mgr.submit("local", REQ)  # 활성 1건 → 검토 시작 불가
    with pytest.raises(QueueFull):
        await mgr.review("local", st.run_id)
    await mgr.wait("local", other.run_id)
    store.claimed.add(("local", st.run_id))  # 다른 프로세스가 run 을 잡고 있다
    with pytest.raises(RunBusy):
        await mgr.review("local", st.run_id)


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
        EditRequest(sentences=[SentenceEdit(sentence_id="s:m:0", action="manual", text="  A  ")]),
        None,
    )
    assert (
        sections[0].sentences[0].text == "A"
        and sections[0].sentences[0].origin == "proposer"
        and used == set()
    )
    with pytest.raises(EditRejected, match="형식"):
        apply_edit_request(
            old.sections,
            EditRequest(sentences=[SentenceEdit(sentence_id="m:0", action="keep")]),
            None,
        )
    with pytest.raises(EditRejected, match="비어"):
        apply_edit_request(
            old.sections,
            EditRequest(sentences=[SentenceEdit(sentence_id="s:m:0", action="manual", text=" ")]),
            None,
        )
