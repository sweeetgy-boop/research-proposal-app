"""전체 흐름 ③~⑥ 의 상태 전이 (domain 규칙, 표 테스트로 고정) — ADR 0011 (2026-10-27).

    queued ──▶ running(생성: 설계도·검색·로컬 작성·규칙 정리) ──▶ v1 저장
      running ──(검토 LLM 있음)──▶ draft_reviewing (Argon 1차 검토)
      running ──draft_written(검토 LLM 없음)──▶ drafted (v1 그대로)
      draft_reviewing ──finish_draft_review──▶ drafted (검증 통과 수정안 자동 반영 → v2)
      draft_reviewing ──fail_draft_review──▶ drafted (v1 유지, 재시도 뒤)
    drafted ──edit──▶ editing ──edit──▶ editing   (④ 직접 수정·보완: 저장·복원, 외부 LLM 없음)
    drafted | editing | final_reviewed ──start_final_review──▶ final_reviewing (⑤ 최신 저장 버전)
      final_reviewing ──finish_final_review──▶ final_reviewed
      final_reviewing ──fail_final_review──▶ (검토 전 상태)
    final_reviewed ──edit──▶ editing   (최종 검토 이후 수정 n건 = stale, 다시 받기는 요청 시만)
    final_reviewed ──finalize──▶ finalized   (⑥ 최종 마무리. stale 이면 경고만)
    drafted | editing ──finalize──▶ finalized   (검토 LLM 없이 건너뛴 경우만 — can_finalize)
    finalized ──finalize──▶ finalized (새 파일)   finalized ──reopen──▶ editing
    검토 중(draft_reviewing·final_reviewing)에는 편집 잠금. 양식 파일은 finalize 로만 (can_render).

이 흐름은 이전의 "재검토 무제한"(done → reviewing(n) → reviewed → editing → …)을 대체한다.
옛 상태 이름은 normalize_status 로 읽는다 (done·reviewed → drafted, reviewing → draft_reviewing).
"""

from __future__ import annotations

from typing import Literal

Event = Literal[
    "draft_written",
    "finish_draft_review",
    "fail_draft_review",
    "edit",
    "start_final_review",
    "finish_final_review",
    "fail_final_review",
    "finalize",
    "reopen",
]

# 초안이 완성된 뒤의 상태들 (검토·편집·마무리 대상)
POST_DRAFT: frozenset[str] = frozenset(
    {"draft_reviewing", "drafted", "editing", "final_reviewing", "final_reviewed", "finalized"}
)
# 편집(제안자 수정·저장·복원)이 허용되는 상태 — 검토 중에는 잠근다
EDITABLE: frozenset[str] = frozenset({"drafted", "editing", "final_reviewed", "finalized"})
# 검토 진행 중 (편집·마무리 잠금)
REVIEWING: frozenset[str] = frozenset({"draft_reviewing", "final_reviewing"})
# 옛 흐름의 상태 이름 → 새 이름 (저장된 run 을 읽을 때)
LEGACY_STATUS: dict[str, str] = {
    "done": "drafted",
    "reviewed": "drafted",
    "reviewing": "draft_reviewing",
}

_TRANSITIONS: dict[tuple[str, str], str] = {
    ("running", "draft_written"): "drafted",  # 검토 LLM 없음 (있으면 start_draft_review)
    ("drafted", "finish_draft_review"): "drafted",  # 방어: 이미 drafted 면 그대로
    ("draft_reviewing", "finish_draft_review"): "drafted",
    ("draft_reviewing", "fail_draft_review"): "drafted",
    ("drafted", "edit"): "editing",
    ("editing", "edit"): "editing",
    ("final_reviewed", "edit"): "editing",  # 최종 검토 이후 수정 → stale 표시
    ("finalized", "edit"): "editing",  # 되돌리기·편집은 reopen 과 같다
    ("drafted", "start_final_review"): "final_reviewing",
    ("editing", "start_final_review"): "final_reviewing",
    ("final_reviewed", "start_final_review"): "final_reviewing",  # 다시 받기 (요청 시만)
    ("final_reviewing", "finish_final_review"): "final_reviewed",
    ("final_reviewed", "finalize"): "finalized",
    ("drafted", "finalize"): "finalized",  # review_skipped 일 때만 — can_finalize 가 지킨다
    ("editing", "finalize"): "finalized",  # review_skipped 일 때만 — can_finalize 가 지킨다
    ("finalized", "finalize"): "finalized",
    ("finalized", "reopen"): "editing",
}
_FAIL_PREVIOUS = {
    "fail_draft_review": "draft_reviewing",
    "fail_final_review": "final_reviewing",
}


class InvalidTransition(ValueError):
    """이 상태에서는 그 동작을 할 수 없다."""


def normalize_status(status: str) -> str:
    """저장된 옛 상태 이름을 새 흐름의 이름으로."""
    return LEGACY_STATUS.get(status, status)


def transition(status: str, event: str, *, previous: str | None = None) -> str:
    """다음 상태. fail_* 는 검토 전 상태(previous)로 돌아간다 (모르면 drafted)."""
    status = normalize_status(status)
    if event in _FAIL_PREVIOUS:
        if status != _FAIL_PREVIOUS[event]:
            raise InvalidTransition(f"{status} 상태에서는 {event} 가 없습니다.")
        if event == "fail_draft_review":
            return "drafted"
        return previous if previous in ("drafted", "editing", "final_reviewed") else "editing"
    if event == "draft_written" and status == "running":
        return "drafted"
    try:
        return _TRANSITIONS[(status, event)]
    except KeyError:
        raise InvalidTransition(hint(status, event)) from None


def start_draft_review(status: str) -> str:
    """생성 직후 1차 검토 시작 — running/drafted 에서만."""
    status = normalize_status(status)
    if status not in ("running", "drafted"):
        raise InvalidTransition(f"{status} 상태에서는 1차 검토를 시작할 수 없습니다.")
    return "draft_reviewing"


def can_edit(status: str) -> bool:
    return normalize_status(status) in EDITABLE


def can_final_review(status: str) -> bool:
    return (normalize_status(status), "start_final_review") in _TRANSITIONS


def can_finalize(status: str, *, final_reviewed: bool, review_skipped: bool) -> bool:
    """⑥ 조건: 최종 검토 완료(final_reviewed)이거나, 검토 LLM 이 없어 건너뛴(review_skipped)
    drafted/editing. 검토 중이면 불가. 저장하지 않은 임시 편집은 유스케이스가 따로 막는다."""
    status = normalize_status(status)
    if status in REVIEWING:
        return False
    if status in ("final_reviewed", "finalized"):
        return True
    if status in ("drafted", "editing"):
        return final_reviewed or review_skipped  # stale(최종 검토 이후 수정)은 경고만
    return False


def can_render(status: str) -> bool:
    """양식 파일은 finalize 결과(finalized)로만 만든다."""
    return normalize_status(status) == "finalized"


_HINTS = {
    "edit": "편집은 초안 완료·수정·최종 검토 완료·마무리 상태에서만 (검토 중에는 불가).",
    "start_final_review": "최종 검토는 초안 완료·수정·최종 검토 완료 상태에서만 요청.",
    "finish_final_review": "최종 검토 중(final_reviewing)이 아닙니다.",
    "finish_draft_review": "1차 검토 중(draft_reviewing)이 아닙니다.",
    "finalize": "최종 마무리는 최종 검토 완료 뒤(또는 검토 건너뜀), 검토 중이 아닐 때만.",
    "reopen": "다시 열기는 최종 마무리(finalized) 상태에서만 할 수 있습니다.",
}


def hint(status: str, event: str) -> str:
    return f"{status} 상태에서는 {event} 를 할 수 없습니다. {_HINTS.get(event, '')}".strip()
