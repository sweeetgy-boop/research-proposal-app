"""작성 → 검토 → 수정 → 재검토 → 최종 마무리 상태 흐름 (domain 규칙, 표 테스트로 고정).

    done ──start_review──▶ reviewing ──finish_review──▶ reviewed ──edit──▶ editing
    editing ──start_review──▶ reviewing(n+1) …   (재검토 횟수 제한 없음)
    done ──skip_review───▶ reviewed (review_skipped)
    reviewing ──fail_review──▶ 검토 전 상태 (done 또는 editing)
    editing/reviewed ──finalize──▶ finalized      finalized ──finalize──▶ finalized (새 파일)
    finalized ──reopen──▶ editing                 reviewed ──edit──▶ editing

재검토 횟수 제한은 없다. 렌더(양식 파일)는 finalize 로만 일어난다 (can_render).
"""

from __future__ import annotations

from typing import Literal

Event = Literal[
    "start_review", "finish_review", "skip_review", "fail_review", "edit", "finalize", "reopen"
]

# 초안이 완성된 뒤의 상태들 (검토·편집·마무리 대상)
POST_DRAFT: frozenset[str] = frozenset({"done", "reviewing", "reviewed", "editing", "finalized"})
# 편집(제안자 수정·되돌리기)이 허용되는 상태
EDITABLE: frozenset[str] = frozenset({"done", "reviewed", "editing", "finalized"})

_TRANSITIONS: dict[tuple[str, str], str] = {
    ("done", "start_review"): "reviewing",
    ("done", "skip_review"): "reviewed",
    ("editing", "start_review"): "reviewing",
    ("editing", "skip_review"): "reviewed",
    ("reviewed", "start_review"): "reviewing",  # 수정 없이 다시 검토
    ("reviewing", "finish_review"): "reviewed",
    ("reviewed", "edit"): "editing",
    ("done", "edit"): "editing",  # 검토 없이(또는 건너뛴 뒤) 바로 손본 경우
    ("editing", "edit"): "editing",
    ("finalized", "edit"): "editing",  # 되돌리기·편집은 reopen 과 같다
    ("reviewed", "finalize"): "finalized",
    ("editing", "finalize"): "finalized",
    ("finalized", "finalize"): "finalized",
    ("finalized", "reopen"): "editing",
}


class InvalidTransition(ValueError):
    """이 상태에서는 그 동작을 할 수 없다."""


def transition(status: str, event: str, *, previous: str | None = None) -> str:
    """다음 상태. fail_review 는 검토 전 상태(previous: done|editing|reviewed)로 돌아간다."""
    if event == "fail_review":
        if status != "reviewing":
            raise InvalidTransition(f"{status} 상태에서는 fail_review 가 없습니다.")
        return previous if previous in ("done", "editing", "reviewed") else "done"
    try:
        return _TRANSITIONS[(status, event)]
    except KeyError:
        raise InvalidTransition(_hint(status, event)) from None


def can_finalize(status: str, *, review_rounds: int, review_skipped: bool) -> bool:
    """검토 1회 이상 완료(또는 건너뜀)이고 검토 진행 중이 아닐 때만."""
    if status == "reviewing":
        return False
    if status not in ("reviewed", "editing", "finalized"):
        return False
    return review_rounds >= 1 or review_skipped


def can_render(status: str) -> bool:
    """양식 파일은 finalize 결과(finalized)로만 만든다."""
    return status == "finalized"


def can_review(status: str) -> bool:
    return (status, "start_review") in _TRANSITIONS


_HINTS = {
    "start_review": "검토는 초안 완료(done)·수정(editing)·검토 완료(reviewed) 상태에서만 시작.",
    "finish_review": "검토 중(reviewing)이 아닙니다.",
    "skip_review": "검토는 초안 완료·수정 상태에서만 건너뛸 수 있습니다.",
    "edit": "편집은 초안 완료·검토 완료·수정·마무리 상태에서만 할 수 있습니다 (검토 중에는 불가).",
    "finalize": "최종 마무리는 검토 1회 이상(또는 건너뜀) 뒤, 검토 중이 아닐 때만 할 수 있습니다.",
    "reopen": "다시 열기는 최종 마무리(finalized) 상태에서만 할 수 있습니다.",
}


def _hint(status: str, event: str) -> str:
    return f"{status} 상태에서는 {event} 를 할 수 없습니다. {_HINTS.get(event, '')}".strip()
