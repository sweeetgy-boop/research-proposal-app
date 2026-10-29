"""홈·내 제안서 표의 과제유형 이름 (UI Research Studio, 레인 2) — 순수 규칙."""

from __future__ import annotations

from rra.domain.models import Section
from rra.domain.rules.run_title import draft_task_type


def test_confirmed_choice_wins_over_draft_suggestion():
    secs = [Section(key="task_type", sentences=[], choices=["basic"])]
    assert draft_task_type(secs, ["applied"]) == "응용연구"


def test_draft_suggestion_when_not_confirmed():
    secs = [
        Section(key="title", sentences=[]),
        Section(key="task_type", sentences=[], choices=["development"]),
    ]
    assert draft_task_type(secs) == "개발연구"
    assert draft_task_type([{"key": "task_type", "choices": ["basic"]}]) == "기초연구"


def test_unknown_or_missing_is_empty():
    assert draft_task_type([Section(key="task_type", sentences=[], choices=["zzz"])], ["no"]) == ""
    assert draft_task_type([]) == ""
