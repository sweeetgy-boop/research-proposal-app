"""문제 정의 카드 응답 직렬화 (ADR 0065, 계약 problem-card.md 3절). 로직 없음.

카드의 글은 AI 출력·제안자 입력(비신뢰) — clean 으로 정리해 내보낸다. 사유·신호는 한국어 라벨을
함께 준다(화면은 내부 코드를 보이지 않는다).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rra.application.usecases.argon_first import reason_label
from rra.application.usecases.problem_card_contract import DiagnoseOutcome, EditOutcome
from rra.domain.models.problem_card import ProblemCard
from rra.domain.rules.problem_card import card_lines, signal_labels

TIMEOUT_LABEL = "응답이 늦어 문제 정의 없이 진행합니다"
FAILED_LABEL = "문제 정의를 만들지 못했습니다 — 그대로 진행할 수 있습니다"
DISABLED_DETAIL = "문제 정의 카드를 쓸 수 없습니다."


def _same(text: str) -> str:
    return text


def _deep(value: Any, clean: Callable[[str], str]) -> Any:
    if isinstance(value, str):
        return clean(value)
    if isinstance(value, list):
        return [_deep(v, clean) for v in value]
    if isinstance(value, dict):
        return {k: _deep(v, clean) for k, v in value.items()}
    return value


def card_payload(card: ProblemCard, *, clean: Callable[[str], str] = _same) -> dict[str, Any]:
    return _deep(card.model_dump(mode="json"), clean)


def _failure_label(reason: str | None) -> str | None:
    if reason is None:
        return None
    if reason == "timeout":
        return TIMEOUT_LABEL
    return reason_label(reason) or FAILED_LABEL


def diagnose_payload(
    outcome: DiagnoseOutcome, *, clean: Callable[[str], str] = _same
) -> dict[str, Any]:
    card = outcome.card if outcome.status == "ok" else None
    return {
        "status": outcome.status,
        "card": card_payload(card, clean=clean) if card is not None else None,
        "lines": _deep(card_lines(card), clean) if card is not None else None,
        "signal_labels": signal_labels(card) if card is not None else [],
        "reason": outcome.reason,
        "reason_label": _failure_label(outcome.reason),
        "provider": outcome.provider,
        "model": outcome.model,
        "fallback_local": outcome.fallback,
        "seconds": outcome.seconds,
        # 재사용한 카드인가(계약 4.4절) — pinned: 확인해 고정한 카드, cached: 전에 만든 카드
        "reused": outcome.reused if card is not None else None,
    }


def off_payload() -> dict[str, Any]:
    return diagnose_payload(DiagnoseOutcome(status="off"))


def edit_payload(outcome: EditOutcome, *, clean: Callable[[str], str] = _same) -> dict[str, Any]:
    return {
        "card": card_payload(outcome.card, clean=clean),
        "lines": _deep(card_lines(outcome.card), clean),
        "signal_labels": signal_labels(outcome.card),
        "reruns": list(outcome.reruns),
        "plans_stale": "plans_stale" in outcome.reruns,
        "recorded": outcome.recorded,
    }
