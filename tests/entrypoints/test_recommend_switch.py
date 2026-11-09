"""② 과제안 갈래 전환 판정 (레인 B, ADR 0061) — 세션의 갈래와 지금 선택으로 계산한 갈래가 다르면
409 code=mode_changed. 갈래 판정은 similar_rows.recommend_mode 한 곳을 그대로 쓴다.
app.py 는 공용 파일이라 여기서는 순수 헬퍼만 시험한다(핸들러 연결은 통합 때 — PR 설명)."""

from __future__ import annotations

import json

import pytest

from rra.domain.models import OverlapAlert, ProposalRequest, RecommendationResult
from rra.domain.rules.problem_labels import PROBLEM_LABELS
from rra.entrypoints.api.recommend_switch import (
    MODE_CHANGED,
    MODE_CHANGED_CODE,
    ModeChanged,
    check_mode_unchanged,
    mode_changed,
    mode_changed_response,
    session_mode,
)

ROW = OverlapAlert(
    doc_id="alio:1", title="기존 과제", tier="external", similarity=0.9, blocking=True
)
BASE = {"current_state": "a", "root_cause": "b", "limitation": "c", "goal": "d"}


def _req(**choices: str) -> ProposalRequest:
    return ProposalRequest(
        **BASE,
        similar_choices=[{"doc_id": d, "choice": c} for d, c in choices.items()],
    )


def test_session_mode_defaults_to_differentiate_for_old_results():
    assert session_mode(RecommendationResult()) == "differentiate"
    assert session_mode(RecommendationResult(mode="novel")) == "novel"
    assert session_mode(object()) == "differentiate"


def test_mode_changed_when_choices_flip_the_branch():
    novel = RecommendationResult(mode="novel")
    diff = RecommendationResult(mode="differentiate")
    # (a) novel 세션 — 차단 행을 [유사함] 으로 두면(또는 선택 없음·차단) 차별화로 바뀐다
    assert mode_changed(novel, [ROW], _req()) is True
    assert mode_changed(novel, [ROW], _req(**{"alio:1": "similar"})) is True
    # 모두 [관련 없음] → 유사함 0·차단 없음 → novel 그대로
    assert mode_changed(novel, [ROW], _req(**{"alio:1": "unrelated"})) is False
    # (b) 차별화 세션 — 차단 행을 모두 [관련 없음] 으로 바꾸면 novel 로 바뀐다
    assert mode_changed(diff, [ROW], _req(**{"alio:1": "unrelated"})) is True
    assert mode_changed(diff, [ROW], _req()) is False
    # 알림이 하나도 없으면 novel — 차별화 세션은 바뀐 것
    assert mode_changed(diff, [], _req()) is True
    assert mode_changed(novel, [], _req()) is False
    # 서버가 novel 을 차별화로 되돌린 세션(novelty_reverted)은 novel 입력의 답 — 전환 아님
    # (되풀이 방지)
    reverted = RecommendationResult(mode="differentiate", novelty_reverted=True)
    assert mode_changed(reverted, [], _req()) is False
    assert mode_changed(reverted, [ROW], _req(**{"alio:1": "unrelated"})) is False
    assert mode_changed(reverted, [ROW], _req()) is False


def test_check_raises_coded_409_and_response_is_problem_json_with_label():
    with pytest.raises(ModeChanged) as info:
        check_mode_unchanged(
            RecommendationResult(mode="differentiate"), [ROW], _req(**{"alio:1": "unrelated"})
        )
    exc = info.value
    assert (exc.session_mode, exc.current_mode) == ("differentiate", "novel")
    resp = mode_changed_response(exc)
    assert resp.status_code == 409 and resp.media_type == "application/problem+json"
    body = json.loads(resp.body)
    assert body["code"] == MODE_CHANGED_CODE == "mode_changed"
    assert body["detail"] == MODE_CHANGED and "과제안을 다시 받습니다" in body["detail"]
    # 코드는 두 표(파이썬·web labels.ts)에 설명이 있다 — 화면은 코드를 그대로 내지 않는다
    assert PROBLEM_LABELS[MODE_CHANGED_CODE] == "선택이 바뀌어 과제안을 다시 받습니다"
    check_mode_unchanged(RecommendationResult(mode="differentiate"), [ROW], _req())  # 같으면 조용히
