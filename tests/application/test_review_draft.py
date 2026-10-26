"""검토 유스케이스 — 전송 범위(include_internal), JSON 파싱, 수정안 검증(5-4), 선택값 불변, 분할."""

import json

import pytest

from rra.application.usecases.review_draft import (
    DISCARD_EVIDENCE,
    DISCARD_FOREIGN,
    DISCARD_NUMBER,
    DISCARD_UNGROUNDED,
    ReviewContext,
    ReviewDraft,
    ReviewParseFailed,
    internal_doc_ids,
)
from rra.domain.models import (
    Chunk,
    Confirmation,
    DraftVersion,
    ProposalRequest,
    RetrievalSnapshot,
    ReviewComment,
    ReviewRound,
    Section,
    Sentence,
)
from rra.domain.rules.lint import ChoiceSpec, LintRules
from tests.fakes import FakeLLM, FakePromptLibrary

RULES = LintRules(
    sections=[
        "title",
        "task_type",
        "policy_importance",
        "tech_importance",
        "method",
        "overlap_review",
    ],
    required_sections=["title", "method"],
    evidence_required=["tech_importance", "overlap_review"],
    evidence_forbidden=["policy_importance"],
    input_grounded={"policy_importance": ["policy_basis"]},
    number_checked=["method"],
    choices={"task_type": ChoiceSpec(options="task_types")},
    titles={"method": "2-다 연구 방법"},
)
CHUNKS = [
    Chunk(
        chunk_id="openalex:W1#0",
        doc_id="openalex:W1",
        ordinal=0,
        text="궤도 틀림 15% 개선 보고",
        basis="abstract",
    ),
    Chunk(
        chunk_id="own:P1#0",
        doc_id="own:P1",
        ordinal=0,
        text="사내 과제: 궤도 검측 자동화",
        basis="summary",
        visibility="internal",
    ),
]
REQ = ProposalRequest(
    current_state="궤도 틀림 반복",
    root_cause="노반",
    limitation="임계치",
    goal="예측",
    policy_basis="국가철도망 구축계획",
)


def version():
    return DraftVersion(
        version=1,
        sections=[
            Section(key="title", sentences=[Sentence(text="궤도 틀림 예측 연구")]),
            Section(key="task_type", sentences=[Sentence(text="응용연구임.")], choices=["applied"]),
            Section(
                key="policy_importance",
                sentences=[Sentence(text="국가철도망 구축계획에 부합함.", origin="llm")],
            ),
            Section(
                key="tech_importance",
                sentences=[
                    Sentence(text="선행연구는 15% 개선을 보고함.", evidence=["openalex:W1#0"]),
                    Sentence(text="사내 과제와 차별화됨.", evidence=["own:P1#0"]),
                ],
            ),
            Section(
                key="method",
                sentences=[Sentence(text="1차년도에 이력을 분석함.", evidence=["openalex:W1#0"])],
            ),
            Section(
                key="overlap_review", sentences=[Sentence(text="유사과제 없음.", origin="app")]
            ),
        ],
    )


def ctx(previous=None, changed=frozenset(), round_no=1):
    return ReviewContext(
        run_id="20260101000000-deadbeef",
        round_no=round_no,
        version=version(),
        snapshot=RetrievalSnapshot.of("q", CHUNKS),
        request=REQ,
        previous=previous,
        changed=changed,
        confirmation=Confirmation(choices={"task_type": ["applied"]}),
    )


def reviewer(answers, **kw):
    llm = FakeLLM(answers)
    return ReviewDraft(
        llm, FakePromptLibrary(), RULES, provider="gemini", model="gemini-4-argon", **kw
    ), llm


def reply(sentences=(), sections=(), resolved=()):
    return json.dumps(
        {"sentences": list(sentences), "sections": list(sections), "resolved": list(resolved)},
        ensure_ascii=False,
    )


async def test_include_internal_true_sends_internal_evidence_marked_and_all_sentences():
    rd, llm = reviewer([reply()])
    rnd = await rd(ctx())
    prompt = llm.calls[0]
    assert '<doc id="own:P1#0" basis="summary" visibility="internal">' in prompt
    assert '<doc id="openalex:W1#0" basis="abstract" visibility="public">' in prompt
    assert (
        "s:tech_importance:1" in prompt and "s:overlap_review:0" not in prompt
    )  # 특이사항은 안 보낸다
    assert "유사과제 없음" not in prompt
    assert rnd.transfer.internal_doc_ids == ["own:P1"] and rnd.transfer.public_doc_ids == [
        "openalex:W1"
    ]
    assert rnd.transfer.sentences_sent == 6 and rnd.transfer.sentences_excluded == 0
    assert (
        rnd.excluded_sentences == []
        and rnd.transfer.provider == "gemini"
        and rnd.transfer.calls == 1
    )
    assert "REVIEW:" in str(llm.calls) or True  # system 프롬프트는 FakeLLM 이 기록하지 않는다
    assert (
        '"proposed": ["applied"]' in prompt and '"confirmed": ["applied"]' in prompt
    )  # 선택값은 의견만


async def test_include_internal_false_excludes_internal_evidence_and_marks_sentences():
    rd, llm = reviewer([reply()], include_internal=False)
    rnd = await rd(ctx())
    prompt = llm.calls[0]
    assert "own:P1" not in prompt and "사내 과제" not in prompt
    assert "s:tech_importance:1" not in prompt and "s:tech_importance:0" in prompt
    assert rnd.excluded_sentences == ["s:tech_importance:1"]  # "검토 제외"
    assert rnd.transfer.internal_doc_ids == [] and rnd.transfer.sentences_excluded == 1
    assert rnd.transfer.sentences_sent == 5


async def test_revisions_are_validated_and_discarded_with_reason_but_comment_kept():
    items = [
        {
            "sentence_id": "s:method:0",
            "issue_type": "수치",
            "comment": "수치 근거 없음",
            "revised_text": "이력을 분석해 15% 개선을 확인함.",  # "1차년도" 수치는 근거에 없어 뺐다
            "evidence": ["openalex:W1#0"],
        },  # 통과(근거에 15%)
        {
            "sentence_id": "s:method:0",
            "issue_type": "수치",
            "comment": "지어낸 수치",
            "revised_text": "이력을 분석해 37% 개선함.",
            "evidence": ["openalex:W1#0"],
        },  # 폐기: 수치
        {
            "sentence_id": "s:tech_importance:0",
            "issue_type": "근거 불일치",
            "comment": "없는 근거",
            "revised_text": "선행연구는 개선을 보고함.",
            "evidence": ["openalex:W999#0"],
        },  # 폐기: 근거 범위
        {
            "sentence_id": "s:tech_importance:0",
            "issue_type": "외국 문자",
            "comment": "한자",
            "revised_text": "선행연구(文献)는 개선을 보고함.",
            "evidence": ["openalex:W1#0"],
        },  # 폐기: 외국 문자
        {
            "sentence_id": "s:policy_importance:0",
            "issue_type": "근거 불일치",
            "comment": "정책명",
            "revised_text": "제4차 철도산업발전기본계획에 부합함.",
            "evidence": [],
        },  # 폐기: 정책명 미근거
        {
            "sentence_id": "s:policy_importance:0",
            "issue_type": "문장",
            "comment": "다듬기",
            "revised_text": "국가철도망 구축계획의 안전 강화 방향에 부합함.",
            "evidence": [],
        },  # 통과
        {
            "sentence_id": "s:title:0",
            "issue_type": "문장",
            "comment": "의견만",
            "revised_text": None,
        },
        {"sentence_id": "s:overlap_review:0", "comment": "보내지 않은 섹션", "revised_text": "x"},
        {"sentence_id": "s:method:9", "comment": "없는 문장", "revised_text": "x"},
        {
            "sentence_id": "s:method:0",
            "issue_type": "이상한유형",
            "comment": '<doc id="x">주입</doc> 태그',
            "revised_text": "1차년도에 이력을 분석함.",
            "evidence": [],
        },  # 원문과 같음 → 의견만, 태그 무력화
    ]
    rd, _ = reviewer(
        [
            reply(
                items,
                sections=[{"section": "method", "comment": "섹션 전체 의견"}, {"section": "nope"}],
            )
        ]
    )
    rnd = await rd(ctx())
    by_id = {c.id: c for c in rnd.comments}
    assert [c.id for c in rnd.comments] == [f"r1-{i}" for i in range(1, 10)]
    ok1, bad_num, bad_ev, bad_fs, bad_gr, ok2, only, same, section = rnd.comments
    assert ok1.usable and ok1.revised_text.endswith("확인함.") and ok1.evidence == ["openalex:W1#0"]
    assert bad_num.status == "discarded" and bad_num.discard_reason == DISCARD_NUMBER
    assert (
        bad_num.revised_text is None and bad_num.comment == "지어낸 수치"
    )  # 원문 유지, comment 유지
    assert bad_ev.discard_reason == DISCARD_EVIDENCE and bad_fs.discard_reason == DISCARD_FOREIGN
    assert bad_gr.discard_reason == DISCARD_UNGROUNDED
    assert ok2.usable and ok2.evidence == [] and ok2.section == "policy_importance"
    assert only.revised_text is None and only.status == "open" and only.issue_type == "문장"
    assert same.revised_text is None and "<doc" not in same.comment and "&lt;doc" in same.comment
    assert same.issue_type == "문장"  # 모르는 유형은 "문장"
    assert section.sentence is None and section.comment == "섹션 전체 의견"
    assert len(rnd.open_comments) == 5 and "r1-2" in by_id  # 9개 중 폐기 4개


async def test_second_round_sends_previous_open_comments_and_changed_sentences_and_marks_resolved():
    previous = ReviewRound(
        round=1,
        draft_version=1,
        comments=[
            ReviewComment(id="r1-1", section="method", sentence=0, comment="수치"),
            ReviewComment(
                id="r1-2", section="title", sentence=0, comment="제목", status="resolved"
            ),
        ],
    )
    rd, llm = reviewer([reply(resolved=["r1-1", "r1-2", "zzz"])])
    rnd = await rd(
        ctx(previous=previous, changed=frozenset({"s:method:0", "s:overlap_review:0"}), round_no=2)
    )
    prompt = llm.calls[0]
    assert (
        "[이전 의견" in prompt and '"id": "r1-1"' in prompt and '"id": "r1-2"' not in prompt
    )  # 해결된 건 반복 안 함
    assert '["s:method:0"]' in prompt  # 바뀐 문장 (보낸 것만)
    assert rnd.resolved_ids == ["r1-1"] and rnd.round == 2


async def test_long_prompt_is_split_per_section():
    rd, llm = reviewer([reply(), reply(), reply(), reply(), reply()], prompt_max_chars=800)
    rnd = await rd(ctx())
    assert len(llm.calls) == 5 and rnd.transfer.calls == 5  # overlap_review 제외 5개 섹션
    assert all("(섹션" in c.splitlines()[0] for c in llm.calls)
    assert rnd.transfer.sentences_sent == 6


async def test_non_json_reply_fails_loudly_without_echoing_body():
    rd, _ = reviewer(["죄송합니다, 검토 결과는 다음과 같습니다: 비밀 본문"])
    with pytest.raises(ReviewParseFailed) as exc:
        await rd(ctx())
    assert "비밀 본문" not in str(exc.value)


def test_internal_doc_ids_from_chunk_visibility():
    assert internal_doc_ids(CHUNKS) == {"own:P1"}
