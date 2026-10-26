"""작성 → 검토 → 수정 → 재검토 → 마무리 상태 흐름 — 표 테스트."""

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
    InvalidTransition,
    can_finalize,
    can_render,
    can_review,
    transition,
)

TABLE = [
    ("done", "start_review", "reviewing"),
    ("done", "skip_review", "reviewed"),
    ("done", "edit", "editing"),
    ("reviewing", "finish_review", "reviewed"),
    ("reviewed", "edit", "editing"),
    ("reviewed", "start_review", "reviewing"),
    ("reviewed", "finalize", "finalized"),
    ("editing", "start_review", "reviewing"),
    ("editing", "skip_review", "reviewed"),
    ("editing", "edit", "editing"),
    ("editing", "finalize", "finalized"),
    ("finalized", "reopen", "editing"),
    ("finalized", "finalize", "finalized"),  # 다시 마무리 = 새 파일
    ("finalized", "edit", "editing"),
]


@pytest.mark.parametrize(("status", "event", "expected"), TABLE)
def test_transition_table(status, event, expected):
    assert transition(status, event) == expected


@pytest.mark.parametrize(
    ("status", "event"),
    [
        ("done", "finalize"),  # 검토 전 마무리 금지
        ("done", "finish_review"),
        ("reviewing", "edit"),  # 검토 중 편집 금지
        ("reviewing", "finalize"),  # 검토 중 마무리 금지
        ("reviewing", "start_review"),
        ("reviewing", "reopen"),
        ("queued", "start_review"),
        ("invalid", "start_review"),
        ("done", "reopen"),
        ("editing", "reopen"),
    ],
)
def test_forbidden_transitions(status, event):
    with pytest.raises(InvalidTransition, match=status):
        transition(status, event)


def test_fail_review_returns_to_the_state_before_review():
    assert transition("reviewing", "fail_review", previous="editing") == "editing"
    assert transition("reviewing", "fail_review", previous="done") == "done"
    assert transition("reviewing", "fail_review", previous="reviewed") == "reviewed"
    assert transition("reviewing", "fail_review", previous=None) == "done"
    with pytest.raises(InvalidTransition):
        transition("done", "fail_review")


def test_unlimited_re_review_cycles():
    status = "done"
    for _ in range(5):  # 4회 이상 연속 재검토
        status = transition(status, "start_review")
        status = transition(status, "finish_review")
        status = transition(status, "edit")
    assert status == "editing" and transition(status, "finalize") == "finalized"


def test_finalize_and_render_guards():
    assert can_finalize("reviewed", review_rounds=1, review_skipped=False)
    assert can_finalize("editing", review_rounds=3, review_skipped=False)
    assert can_finalize("reviewed", review_rounds=0, review_skipped=True)  # 건너뜀도 허용
    assert can_finalize("finalized", review_rounds=1, review_skipped=False)
    assert not can_finalize("reviewing", review_rounds=2, review_skipped=False)  # 검토 중
    assert not can_finalize("done", review_rounds=0, review_skipped=False)  # 검토 전
    assert not can_finalize("editing", review_rounds=0, review_skipped=False)
    assert can_render("finalized") and not can_render("reviewed") and not can_render("done")
    assert can_review("done") and can_review("editing") and not can_review("reviewing")
    assert "reviewing" in POST_DRAFT and "reviewing" not in EDITABLE and "finalized" in EDITABLE


def test_review_models_and_sentence_ids():
    assert sentence_id("method", 2) == "s:method:2"
    assert parse_sentence_id("s:method:2") == ("method", 2)
    assert parse_sentence_id("method:2") is None and parse_sentence_id("s:method:x") is None
    usable = ReviewComment(id="r1-1", section="method", sentence=0, revised_text="고친 문장")
    discarded = ReviewComment(
        id="r1-2", section="method", sentence=1, status="discarded", discard_reason="numbers"
    )
    assert usable.usable and not discarded.usable
    assert not ReviewComment(id="r1-3", section="method", sentence=2, comment="의견만").usable
    rnd = ReviewRound(round=1, draft_version=1, comments=[usable, discarded])
    assert rnd.comment("r1-2") is discarded and rnd.open_comments == [usable]
    with pytest.raises(ValueError):
        ReviewRound(round=0, draft_version=1)
    v = DraftVersion(version=1, sections=[])
    assert v.origin == "local" and v.section("x") is None
