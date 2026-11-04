"""② [유사함] 한 규칙 (ADR 0054) — 제안자 선택이 이기고, 없으면 AI 판정의 기본 선택.

같다·일부 겹침 → [유사함], 다르다 → [관련 없음], AI 판정 없음(규칙 판정·AI 실패·판정 전) →
유사함 아님.
차단 게이트는 제안자 선택만 본다(차단 행을 모두 [관련 없음] 으로 골라야 풀린다).
"""

from __future__ import annotations

import pytest

from rra.domain.models import OverlapAlert
from rra.domain.rules import similar_choice as sc
from rra.domain.rules.precheck_levels import default_choices


def _row(doc_id="own:1", *, judgment=None, judged_by=None, blocking=False, merged=()):
    return OverlapAlert(
        doc_id=doc_id,
        title="t",
        tier="own",
        similarity=0.85,
        blocking=blocking,
        judgment=judgment,
        judged_by=judged_by,
        merged_ids=list(merged),
    )


@pytest.mark.parametrize(
    ("judgment", "judged_by", "user", "expected"),
    [
        # 제안자 선택이 이긴다
        ("same", "argon", "unrelated", "unrelated"),
        ("partial", "argon", "unrelated", "unrelated"),
        ("different", "argon", "similar", "similar"),
        (None, "rule", "similar", "similar"),
        (None, None, "unrelated", "unrelated"),
        # 선택이 없으면 AI 기본 선택
        ("same", "argon", None, "similar"),
        ("partial", "local", None, "similar"),
        ("different", "argon", None, "unrelated"),
        # AI 판정 없음 → 유사함 아님
        (None, "rule", None, None),
        (None, None, None, None),
    ],
)
def test_effective_choice_table(judgment, judged_by, user, expected):
    row = _row(judgment=judgment, judged_by=judged_by)
    choices = {row.doc_id: user} if user else {}
    assert sc.effective_choice(row, choices) == expected
    assert (row in sc.effective_similar([row], choices)) is (expected == sc.SIMILAR)


def test_rule_judged_row_never_gets_a_default_even_with_a_stale_verdict():
    """judged_by=rule(AI 실패 → 규칙 기준)이면 판정 칸이 남아 있어도 기본 선택 없음."""
    assert sc.default_choice(_row(judgment="same", judged_by="rule")) is None


def test_merged_row_choice_by_member_id_wins_over_default():
    row = _row("own:1", judgment="partial", judged_by="argon", merged=["own:2"])
    assert sc.effective_choice(row, {"own:2": "unrelated"}) == "unrelated"


def test_default_choices_cover_same_partial_and_different_only():
    rows = [
        _row("a", judgment="same", judged_by="argon", blocking=True),
        _row("b", judgment="partial", judged_by="argon"),
        _row("c", judgment="different", judged_by="local"),
        _row("d", judged_by="rule", blocking=True),
        _row("e"),
    ]
    assert default_choices(rows) == {"a": "similar", "b": "similar", "c": "unrelated"}


def test_blocking_gate_uses_user_choices_only():
    """같다(차단) 행의 기본 선택은 [유사함] — 차단은 그대로. 제안자 [관련 없음] 만 푼다."""
    same = _row("a", judgment="same", judged_by="argon", blocking=True)
    other = _row("b", judgment="different", judged_by="argon")
    assert sc.effective_blocking([same, other], {})
    assert sc.effective_blocking([same, other], {"b": "unrelated"})
    assert not sc.effective_blocking([same, other], {"a": "unrelated"})
    _, released = sc.apply_choices([same, other], {"a": "unrelated"})
    assert released


def test_choice_records_keep_only_user_choices_not_defaults():
    """선택 기록(similar_choices.jsonl)은 제안자가 보낸 선택만 — AI 기본 선택은 남기지 않는다."""
    rows = [
        _row("a", judgment="same", judged_by="argon", blocking=True),
        _row("b", judgment="partial", judged_by="argon"),
    ]
    recs = sc.choice_records(rows, {"a": "unrelated"}, idea="h" * 16, at="t")
    assert [(r["doc_id"], r["choice"]) for r in recs] == [("a", "unrelated")]
