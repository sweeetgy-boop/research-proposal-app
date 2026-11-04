"""② 선택 기록 event·중복 한 줄 규칙 (ADR 0056 2026-11-04 후속) — 순수 함수 + 메모리 상태.

- choice_records 는 줄마다 event(generate 기본 | apply).
- choice_signature = event + (doc_id, 선택, 출처) 집합 — 점수·시각·순서는 보지 않는다.
- is_repeat: 마지막 서명과 같으면 건너뛴다. 사이에 다른 서명이 오면 다시 쓴다.
- session_key: 주체 키 원문을 담지 않는 해시.
메모리 상태(ChoiceDedupe)는 tests/entrypoints/test_choice_dedupe.py.
"""

from __future__ import annotations

import pytest

from rra.domain.models import OverlapAlert
from rra.domain.rules import similar_choice as sc


def _row(doc_id: str, **over) -> OverlapAlert:
    base = {
        "doc_id": doc_id,
        "title": f"과제 {doc_id}",
        "tier": "own",
        "similarity": 0.85,
        "blocking": False,
        "keywords": ["궤도"],
    }
    return OverlapAlert(**{**base, **over})


ROWS = [_row("a", blocking=True), _row("b"), _row("c")]


def _recs(choices, sources=None, *, event=sc.EVENT_GENERATE, at="t", rows=ROWS):
    return sc.choice_records(rows, choices, idea="h" * 16, at=at, sources=sources, event=event)


def test_records_carry_event_default_generate_and_reject_unknown():
    assert {r["event"] for r in _recs({"a": "similar"})} == {"generate"}
    assert {r["event"] for r in _recs({"a": "similar"}, event=sc.EVENT_APPLY)} == {"apply"}
    with pytest.raises(ValueError):
        _recs({"a": "similar"}, event="view")


def test_signature_is_event_plus_choice_set_not_scores_time_or_order():
    choices = {"a": "unrelated", "b": "similar"}
    sources = {"a": "user", "b": "ai_prefill"}
    base = sc.choice_signature(_recs(choices, sources, event=sc.EVENT_APPLY))
    # 시각·점수·행 순서가 달라도 같은 서명
    rescored = [_row("b", similarity=0.5), _row("a", blocking=True, rerank_score=0.9), _row("c")]
    assert sc.choice_signature(_recs(choices, sources, event=sc.EVENT_APPLY, at="u")) == base
    assert sc.choice_signature(_recs(choices, sources, event=sc.EVENT_APPLY, rows=rescored)) == base
    # 선택·출처·행 집합·event 가 다르면 다른 서명
    assert sc.choice_signature(_recs({**choices, "b": "unrelated"}, sources, event="apply")) != base
    assert sc.choice_signature(_recs(choices, {**sources, "b": "user"}, event="apply")) != base
    assert sc.choice_signature(_recs({"a": "unrelated"}, sources, event="apply")) != base
    assert sc.choice_signature(_recs(choices, sources, event=sc.EVENT_GENERATE)) != base
    # 줄이 없으면 서명 없음
    assert sc.choice_signature([]) is None


def test_old_lines_without_event_or_source_sign_as_generate_user():
    new = _recs({"a": "similar"})
    old = [{k: v for k, v in r.items() if k not in ("event", "source")} for r in new]
    assert sc.choice_signature(old) == sc.choice_signature(new)


def test_is_repeat_same_skipped_different_resets():
    s1 = sc.choice_signature(_recs({"a": "similar"}, event="apply"))
    s2 = sc.choice_signature(_recs({"a": "unrelated"}, event="apply"))
    assert sc.is_repeat(None, s1) is False
    assert sc.is_repeat(s1, s1) is True
    assert sc.is_repeat(s2, s1) is False
    assert sc.is_repeat(s1, None) is False  # 쓸 줄 없음 — 반복 아님


def test_session_key_hides_owner_and_separates_ideas():
    k = sc.session_key("staff:abcdef123456", "h" * 16)
    assert len(k) == sc.SESSION_KEY_CHARS and "staff" not in k and "abcdef" not in k
    assert k != sc.session_key("staff:abcdef123456", "g" * 16)
    assert k != sc.session_key("staff:other", "h" * 16)
    assert k == sc.session_key("staff:abcdef123456", "h" * 16)
