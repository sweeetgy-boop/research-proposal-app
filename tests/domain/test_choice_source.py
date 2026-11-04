"""② 선택 출처 (ADR 0056) — 선택 기록 줄마다 source(user | ai_prefill).

- 요청: SimilarChoice.source, 보내지 않으면 user (옛 웹 캐시·CLI·MCP 의 명시적 선택).
- 기록: choice_records 가 줄마다 그 선택의 출처를 쓴다. 서버의 AI 기본 선택은 여전히 남기지 않는다.
- 출처는 메타데이터 — 차단 게이트·유효 선택·건수·③ 판정표는 출처와 상관없이 같다.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rra.application.usecases.similar_rows import similar_count, similar_rows
from rra.domain.models import OverlapAlert
from rra.domain.models.request import ProposalRequest, SimilarChoice
from rra.domain.rules import similar_choice as sc

IDEA = {"current_state": "a", "root_cause": "b", "limitation": "c", "goal": "d"}


def _row(doc_id, *, judgment=None, judged_by="argon", blocking=False, merged=()):
    return OverlapAlert(
        doc_id=doc_id,
        title=f"t-{doc_id}",
        tier="own",
        similarity=0.85,
        blocking=blocking,
        judgment=judgment,
        judged_by=judged_by,
        merged_ids=list(merged),
    )


ROWS = [
    _row("a", judgment="same", blocking=True),
    _row("b", judgment="partial"),
    _row("c", judgment="different"),
    _row("d", judgment=None, judged_by="rule"),
]


def test_source_defaults_to_user_when_omitted():
    """옛 웹 캐시·CLI·MCP 가 넘긴 선택(source 없음)은 명시적 선택 — user."""
    assert SimilarChoice(doc_id="own:1", choice="similar").source == "user"
    req = ProposalRequest(**IDEA, similar_choices=[{"doc_id": "own:1", "choice": "unrelated"}])
    assert req.choice_sources() == {"own:1": "user"}
    assert "user" in (SimilarChoice.model_fields["source"].description or "")


def test_source_accepts_only_user_or_ai_prefill():
    ok = SimilarChoice(doc_id="own:1", choice="similar", source="ai_prefill")
    assert ok.source == "ai_prefill"
    with pytest.raises(ValidationError):
        SimilarChoice(doc_id="own:1", choice="similar", source="server_default")


def test_duplicate_doc_id_keeps_last_choice_and_its_source():
    req = ProposalRequest(
        **IDEA,
        similar_choices=[
            {"doc_id": "own:1", "choice": "similar", "source": "ai_prefill"},
            {"doc_id": "own:1", "choice": "unrelated", "source": "user"},
        ],
    )
    assert req.choice_map() == {"own:1": "unrelated"}
    assert req.choice_sources() == {"own:1": "user"}


def test_choice_records_write_source_per_line_prefill_vs_user():
    """미리 고른 값이 남은 행은 ai_prefill, 바꾼 행·기본 선택 없는 행에서 고른 값은 user."""
    req = ProposalRequest(
        **IDEA,
        similar_choices=[
            {
                "doc_id": "a",
                "choice": "similar",
                "source": "ai_prefill",
            },  # 같다 → 미리 고른 [유사함]
            {"doc_id": "b", "choice": "unrelated", "source": "user"},  # 일부 겹침 → 바꿈
            {"doc_id": "c", "choice": "unrelated", "source": "ai_prefill"},  # 다르다 → 그대로
            {"doc_id": "d", "choice": "similar"},  # 규칙 판정 행(기본 선택 없음) — 생략 = user
        ],
    )
    recs = sc.choice_records(
        ROWS, req.choice_map(), idea="h" * 16, at="t", sources=req.choice_sources()
    )
    assert [(r["doc_id"], r["choice"], r["source"]) for r in recs] == [
        ("a", "similar", "ai_prefill"),
        ("b", "unrelated", "user"),
        ("c", "unrelated", "ai_prefill"),
        ("d", "similar", "user"),
    ]


def test_choice_records_default_source_user_and_never_log_server_defaults():
    """sources 를 주지 않아도 줄마다 source(user). 고르지 않은 행(서버 기본 선택)은 줄이 없다."""
    recs = sc.choice_records(ROWS, {"b": "unrelated"}, idea="h" * 16, at="t")
    assert [(r["doc_id"], r["source"]) for r in recs] == [("b", "user")]


def test_choice_records_source_follows_the_merged_member_that_holds_the_choice():
    """묶음 행의 선택이 구성원 doc_id 에 걸려 있으면 그 doc_id 의 출처."""
    rows = [_row("lead", judgment="partial", merged=("member",))]
    recs = sc.choice_records(
        rows,
        {"member": "unrelated"},
        idea="h" * 16,
        at="t",
        sources={"member": "ai_prefill", "lead": "user"},
    )
    assert [(r["doc_id"], r["choice"], r["source"]) for r in recs] == [
        ("lead", "unrelated", "ai_prefill")
    ]


def test_choice_record_keys_are_allowed_by_the_log():
    from rra.adapters.logging.choice_log import ALLOWED_KEYS

    recs = sc.choice_records(ROWS, {"a": "similar"}, idea="h" * 16, at="t", sources={})
    assert set(recs[0]) <= ALLOWED_KEYS and "source" in ALLOWED_KEYS


@pytest.mark.parametrize("source", ["user", "ai_prefill", None])
def test_source_is_metadata_only_gate_choice_and_counts_unchanged(source):
    """출처를 바꿔도(또는 빼도) 차단 게이트·유효 선택·건수·③ 판정표·해제는 같다."""
    picks = [
        {"doc_id": "a", "choice": "unrelated"},
        {"doc_id": "b", "choice": "similar"},
        {"doc_id": "d", "choice": "similar"},
    ]
    if source is not None:
        picks = [{**p, "source": source} for p in picks]
    base = ProposalRequest(
        **IDEA, similar_choices=[{k: v for k, v in p.items() if k != "source"} for p in picks]
    )
    req = ProposalRequest(**IDEA, similar_choices=picks)
    assert req.choice_map() == base.choice_map()
    assert req.prompt_view() == base.prompt_view()
    choices = req.choice_map()
    assert sc.effective_blocking(ROWS, choices) is False
    assert [sc.effective_choice(a, choices) for a in ROWS] == [
        "unrelated",
        "similar",
        "unrelated",
        "similar",
    ]
    assert similar_count(ROWS, choices) == 2
    assert [a.doc_id for a in similar_rows(ROWS, choices)] == ["b", "d"]
    shown, released = sc.apply_choices(ROWS, choices)
    assert released is True and not any(a.blocking for a in shown)
    assert [a.doc_id for a in sc.rows_for_writing(ROWS, choices)] == ["b", "c", "d"]
    # 기록 줄도 source 만 다르다
    with_src = sc.choice_records(ROWS, choices, idea="h" * 16, at="t", sources=req.choice_sources())
    without = sc.choice_records(ROWS, choices, idea="h" * 16, at="t")
    assert [{k: v for k, v in r.items() if k != "source"} for r in with_src] == [
        {k: v for k, v in r.items() if k != "source"} for r in without
    ]
