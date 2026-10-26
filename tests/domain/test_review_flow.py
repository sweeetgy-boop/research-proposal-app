"""전체 흐름 ③~⑥ 상태 전이 — 표 테스트 (ADR 0011: 1차 검토 자동 → 편집 → 최종 검토 1회 → 마무리)."""

import pytest

from rra.domain.models.review import (
    DraftVersion,
    ReviewComment,
    ReviewRound,
    parse_sentence_id,
    sentence_id,
)
from rra.domain.rules.review_flow import (
    EDITABLE,
    POST_DRAFT,
    REVIEWING,
    InvalidTransition,
    can_edit,
    can_final_review,
    can_finalize,
    can_render,
    normalize_status,
    start_draft_review,
    transition,
)

TABLE = [
    ("running", "draft_written", "drafted"),  # 검토 LLM 없음
    ("draft_reviewing", "finish_draft_review", "drafted"),  # v2 (Argon 보완)
    ("draft_reviewing", "fail_draft_review", "drafted"),  # v1 유지
    ("drafted", "edit", "editing"),
    ("editing", "edit", "editing"),
    ("drafted", "start_final_review", "final_reviewing"),
    ("editing", "start_final_review", "final_reviewing"),
    ("final_reviewed", "start_final_review", "final_reviewing"),  # 다시 받기 (요청 시만)
    ("final_reviewing", "finish_final_review", "final_reviewed"),
    ("final_reviewed", "edit", "editing"),  # 최종 검토 이후 수정 → stale
    ("final_reviewed", "finalize", "finalized"),
    ("drafted", "finalize", "finalized"),  # review_skipped 일 때만 — can_finalize 가 지킨다
    ("editing", "finalize", "finalized"),  # review_skipped 일 때만
    ("finalized", "finalize", "finalized"),  # 다시 마무리 = 새 파일
    ("finalized", "reopen", "editing"),
    ("finalized", "edit", "editing"),
    # 옛 이름은 변환해서 받는다
    ("done", "edit", "editing"),
    ("reviewed", "start_final_review", "final_reviewing"),
    ("reviewing", "finish_draft_review", "drafted"),
]


@pytest.mark.parametrize(("status", "event", "expected"), TABLE)
def test_transition_table(status, event, expected):
    assert transition(status, event) == expected


@pytest.mark.parametrize(
    ("status", "event"),
    [
        ("draft_reviewing", "edit"),  # 검토 중 편집 금지
        ("final_reviewing", "edit"),
        ("draft_reviewing", "finalize"),
        ("final_reviewing", "finalize"),
        ("final_reviewing", "start_final_review"),
        ("draft_reviewing", "start_final_review"),  # 1차 검토가 끝나야 최종 검토
        ("queued", "start_final_review"),
        ("invalid", "start_final_review"),
        ("drafted", "reopen"),
        ("editing", "reopen"),
        ("drafted", "finish_final_review"),
        ("editing", "finish_draft_review"),
    ],
)
def test_forbidden_transitions(status, event):
    with pytest.raises(InvalidTransition, match=status):
        transition(status, event)


def test_fail_review_returns_to_the_state_before_review():
    assert transition("draft_reviewing", "fail_draft_review") == "drafted"
    assert transition("final_reviewing", "fail_final_review", previous="editing") == "editing"
    assert transition("final_reviewing", "fail_final_review", previous="drafted") == "drafted"
    assert (
        transition("final_reviewing", "fail_final_review", previous="final_reviewed")
        == "final_reviewed"
    )
    assert transition("final_reviewing", "fail_final_review", previous=None) == "editing"
    with pytest.raises(InvalidTransition):
        transition("drafted", "fail_draft_review")
    with pytest.raises(InvalidTransition):
        transition("editing", "fail_final_review")


def test_start_draft_review_only_right_after_generation():
    assert start_draft_review("running") == "draft_reviewing"
    assert start_draft_review("drafted") == "draft_reviewing"  # 1차 검토를 나중에 돌리는 경우
    with pytest.raises(InvalidTransition):
        start_draft_review("editing")
    with pytest.raises(InvalidTransition):
        start_draft_review("final_reviewed")


def test_final_review_is_once_on_request_and_edit_afterwards_is_allowed_but_stale():
    status = transition("drafted", "edit")
    status = transition(status, "start_final_review")
    status = transition(status, "finish_final_review")
    assert status == "final_reviewed" and can_finalize(
        status, final_reviewed=True, review_skipped=False
    )
    status = transition(status, "edit")  # 최종 검토 이후 수정 — 강제 재검토 없음
    assert status == "editing" and can_final_review(status)
    assert can_finalize(status, final_reviewed=True, review_skipped=False)  # stale — 경고만
    status = transition(status, "start_final_review")  # 원할 때만 다시 받는다
    assert transition(status, "finish_final_review") == "final_reviewed"


def test_can_finalize_conditions():
    # 최종 검토 완료 → 가능. 검토 중 → 불가.
    assert can_finalize("final_reviewed", final_reviewed=True, review_skipped=False)
    assert not can_finalize("final_reviewing", final_reviewed=True, review_skipped=False)
    assert not can_finalize("draft_reviewing", final_reviewed=False, review_skipped=False)
    # 검토 LLM 이 없어 건너뛴 경우에만 drafted/editing 에서 바로 마무리
    assert can_finalize("drafted", final_reviewed=False, review_skipped=True)
    assert can_finalize("editing", final_reviewed=False, review_skipped=True)
    assert not can_finalize("drafted", final_reviewed=False, review_skipped=False)
    assert not can_finalize("editing", final_reviewed=False, review_skipped=False)
    assert can_finalize("editing", final_reviewed=True, review_skipped=False)  # 최종 검토 뒤 수정
    assert can_finalize("finalized", final_reviewed=True, review_skipped=False)  # 다시 마무리
    assert not can_finalize("running", final_reviewed=False, review_skipped=True)


def test_editing_is_locked_during_reviews_and_render_only_when_finalized():
    assert REVIEWING == {"draft_reviewing", "final_reviewing"}
    assert all(not can_edit(s) for s in REVIEWING)
    assert EDITABLE == {"drafted", "editing", "final_reviewed", "finalized"}
    assert can_edit("done") and can_edit("reviewed")  # 옛 이름
    assert POST_DRAFT >= EDITABLE | REVIEWING
    assert can_render("finalized") and not can_render("final_reviewed")
    assert can_final_review("drafted") and not can_final_review("finalized")


def test_legacy_status_names_are_normalized():
    assert normalize_status("done") == "drafted"
    assert normalize_status("reviewed") == "drafted"
    assert normalize_status("reviewing") == "draft_reviewing"
    assert normalize_status("editing") == "editing"


def test_sentence_id_round_trip_and_models():
    assert sentence_id("method", 2) == "s:method:2"
    assert parse_sentence_id("s:method:2") == ("method", 2)
    assert parse_sentence_id("method:2") is None and parse_sentence_id("s:m:x") is None
    c = ReviewComment(id="r1-1", section="method", sentence=0, comment="c", revised_text="r")
    assert c.usable
    rnd = ReviewRound(round=1, draft_version=1, comments=[c])
    assert rnd.kind == "draft" and rnd.final_round is None and rnd.open_comments == [c]
    final = ReviewRound(round=3, kind="final", draft_version=4)
    assert final.final_round == 2
    v = DraftVersion(version=2, origin="argon", sections=[])
    assert v.sentence_count == 0 and v.open_annotations == 0
