"""문제 정의 카드 수정 기록·본인 예시 규칙 (ADR 0065, 계약 problem-card.md 6절)."""

from __future__ import annotations

from rra.domain.rules import card_edits
from rra.domain.rules.feedback_stats import choice_stats

ME, OTHER = "staff:aaaaaaaaaaaa", "staff:bbbbbbbbbbbb"


def rec(user=ME, **kw):
    base = {
        "at": "2026-11-10T00:00:00+00:00",
        "user": user,
        "test": False,
        "idea": "0123456789abcdef",
        "field": "function_ko",
        "before": "비둘기를 쫓는다",
        "after": "조류의 착좌를 막는다",
        "similarity": 0.71,
        "function": "비둘기를 쫓는다",
        "methods": ["core"],
        "signals": [],
    }
    return {**base, **kw}


def test_edit_record_has_only_allowed_keys_and_strips_personal_data():
    row = card_edits.edit_record(
        at="t",
        user=ME,
        test=False,
        idea="h",
        field="cause",
        before="담당자 홍길동 과장 010-1234-5678 에게 확인",
        after="출입구 개방 mail@example.com",
        similarity=0.123456,
        function="비둘기 침입을 막는다",
        methods=["core"],
        signals=["unclear_cause"],
    )
    assert set(row) == card_edits.EDIT_KEYS
    assert "010-1234-5678" not in row["before"] and "mail@example.com" not in row["after"]
    assert row["similarity"] == 0.1235 and row["test"] is False


def test_choice_line_is_summary_of_80_chars_and_test_key_only_when_true():
    line = card_edits.choice_line(
        at="t",
        idea="h",
        field="cause",
        before="가" * 200,
        after="나" * 200,
        methods=["core"],
        signals=[],
        test=False,
    )
    assert line["event"] == "card_edit" and "test" not in line and "user" not in line
    assert len(line["before"]) == 80 and len(line["after"]) == 80
    assert (
        card_edits.choice_line(
            at="t",
            idea="h",
            field="cause",
            before="a",
            after="b",
            methods=[],
            signals=[],
            test=True,
        )["test"]
        is True
    )


def test_is_polish_by_threshold():
    assert card_edits.is_polish(0.95, 0.95) and card_edits.is_polish(0.99, 0.95)
    assert not card_edits.is_polish(0.94, 0.95)
    assert not card_edits.is_polish(None, 0.95) and not card_edits.is_polish(True, 0.95)


def test_cosine():
    assert card_edits.cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert card_edits.cosine([1.0, 0.0], [0.0, 2.0]) == 0.0
    assert card_edits.cosine([], []) is None and card_edits.cosine([0.0], [1.0]) is None
    assert card_edits.cosine([1.0], [1.0, 2.0]) is None


def test_learnable_excludes_other_users_test_lines_polish_and_no_change():
    rows = [
        rec(),
        rec(user=OTHER),
        rec(test=True),
        rec(similarity=0.97),
        rec(after=""),
        rec(before="같음", after="같음"),
        rec(similarity=None),
    ]
    got = card_edits.learnable(rows, user=ME, polish_similarity=0.95)
    assert got == [rows[0], rows[6]]
    assert card_edits.learnable(rows, user="", polish_similarity=0.95) == []


def test_pick_examples_top_n_above_threshold_and_never_other_users():
    rows = [rec(after="A"), rec(after="B"), rec(user=OTHER, after="남의 것"), rec(after="C")]
    got = card_edits.pick_examples(
        rows,
        [0.81, 0.93, 0.99, 0.5],
        user=ME,
        min_similarity=0.8,
        polish_similarity=0.95,
        limit=3,
    )
    assert [r["after"] for r in got] == ["B", "A"]
    one = card_edits.pick_examples(
        rows, [0.81, 0.93, 0.99, 0.9], user=ME, min_similarity=0.8, polish_similarity=0.95, limit=1
    )
    assert [r["after"] for r in one] == ["B"]
    assert (
        card_edits.pick_examples(
            rows, [1, 1, 1, 1], user=ME, min_similarity=0.8, polish_similarity=0.95, limit=0
        )
        == []
    )


def test_examples_block_uses_korean_field_labels():
    block = card_edits.examples_block([rec()], {"function_ko": "기능 문장"})
    assert block == "- 기능 문장: 비둘기를 쫓는다 → 조류의 착좌를 막는다"
    assert card_edits.examples_block([], {}) == ""


def test_feedback_stats_counts_card_edit_only_when_present():
    base = [{"event": "apply", "source": "user"}, {"event": "generate", "source": "user"}]
    assert choice_stats(base).by_event == {"apply": 1, "generate": 1}  # 종전 출력 그대로
    stats = choice_stats([*base, {"event": "card_edit"}, {"event": "card_edit", "test": True}])
    assert stats.by_event == {"apply": 1, "generate": 1, "card_edit": 1}
    assert stats.by_source == {"user": 2, "ai_prefill": 0}
    assert stats.total == 3 and stats.test_lines == 1


def test_strip_contacts_keeps_ordinary_phrases_and_removes_contacts():
    assert card_edits.strip_contacts("차단 효과") == "차단 효과"
    assert card_edits.strip_contacts("미관과 유지관리") == "미관과 유지관리"
    out = card_edits.strip_contacts("미관과 유지관리 문의 010-1234-5678 mail@example.com")
    assert "010-1234-5678" not in out and "mail@example.com" not in out and "유지관리" in out
    assert "홍길동" not in card_edits.strip_contacts("담당자 홍길동 에게 확인")
