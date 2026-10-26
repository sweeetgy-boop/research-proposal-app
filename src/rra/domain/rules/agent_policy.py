"""Agent 의 Tool 호출 조건 — 기획서 Ⅲ "Tool 호출 조건" 표를 코드로 옮긴 규칙.

Tool 을 언제 부를지는 LLM 이 아니라 이 규칙이 정한다.
- 재현 가능하고 테스트할 수 있다.
- 보안 A: 수집 문서(비신뢰 텍스트)가 도구 호출을 조종할 경로가 없다. 생성 LLM 에는 도구 권한이 없다.
- 2분 걸리는 생성에 판단용 LLM 호출을 더하지 않는다.

화면·MCP 호스트는 사람의 사건(아이디어 입력, 진행 선택, 자료 질의, 확정)을 넘기고,
여기서 돌려준 Decision 대로 Tool 을 호출한 뒤 그 기록을 "Agent 활동 기록"으로 보여 준다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rra.domain.models import OverlapAlert, ProposalRequest

Tool = Literal[
    "rra_precheck",
    "rra_search",
    "rra_generate",
    "rra_get_draft",
    "rra_confirm",
    "rra_review",
    "rra_edit",
    "rra_finalize",
    "rra_reopen",
]


@dataclass(frozen=True)
class Decision:
    condition: str  # 기획서 표의 조건
    action: str  # Agent 동작
    tool: Tool | None = None  # 호출할 Tool. None 이면 표시·대기만
    needs_human: bool = False  # 사람 확인 전에는 다음 Tool 을 부르지 않는다


def has_blocking(alerts: list[OverlapAlert]) -> bool:
    return any(a.blocking for a in alerts)


def may_generate(alerts: list[OverlapAlert], *, acknowledged: bool) -> bool:
    """차단 경보가 없거나, 있어도 담당자가 확인했을 때만 생성한다."""
    return acknowledged or not has_blocking(alerts)


def on_intake() -> Decision:
    return Decision(
        "아이디어 입력 수신", "rra_precheck 호출 → 유사과제 경보를 먼저 표시", "rra_precheck"
    )


def after_precheck(
    alerts: list[OverlapAlert],
    req: ProposalRequest,
    *,
    corpus_size: int,
    acknowledged: bool = False,
) -> list[Decision]:
    """precheck 결과를 본 뒤의 판단. 순서대로 화면에 보인다."""
    out: list[Decision] = []
    if has_blocking(alerts) and not acknowledged:
        out.append(
            Decision(
                "기준 초과(차단) 경보 있음",
                "초안 생성 전 담당자 확인 요청. 중복 여부 최종 판단은 사람이 함",
                needs_human=True,
            )
        )
    else:
        out.append(
            Decision(
                "경보 없음 또는 담당자가 진행 선택",
                "rra_generate 호출(백그라운드) → rra_get_draft 로 진행 상황·초안 조회",
                "rra_generate",
            )
        )
    if not req.policy_basis.strip():
        out.append(Decision("정책 근거 미입력", "정책적 중요도 섹션은 생성하지 않고 빈칸 + 경고"))
    if corpus_size <= 0:
        out.append(
            Decision(
                "비교할 수집 자료 없음",
                '특이사항에 "검토를 수행하지 못함" 표시, 근거 필수 섹션 문장 생성 안 함',
            )
        )
    return out


def on_query() -> Decision:
    return Decision(
        "담당자의 자료 질의", "rra_search 호출 → 출처 id 와 함께 근거 구간 제시", "rra_search"
    )


def on_confirm() -> Decision:
    return Decision("담당자의 선택형 항목 확정", "rra_confirm 호출 → 확정값 저장", "rra_confirm")


# ── [5] 작성 → 검토 → 수정 → 재검토 → 마무리 ────────────────
def after_draft_done(*, review_available: bool, auto: bool = True) -> Decision:
    """초안 완료 뒤. 검토 LLM 을 쓸 수 있으면 1차 검토(rra_review), 없으면 건너뜀 기록."""
    if not review_available:
        return Decision(
            "초안 완료 + review 사용 불가(키 없음 등)",
            "검토를 건너뛰고 review_skipped 기록 → 바로 마무리 가능",
        )
    if auto:
        return Decision("초안 완료 + review 사용 가능", "rra_review 호출 (1차, 자동)", "rra_review")
    return Decision(
        "초안 완료 + review 사용 가능 (자동 검토 꺼짐)",
        "담당자가 검토 시작을 선택하면 rra_review 호출",
        "rra_review",
        needs_human=True,
    )


def on_edit(*, rereview: bool, round_no: int) -> Decision:
    """편집 반영 뒤. 재검토를 요청했으면 rra_review(n+1), 아니면 마무리 대기."""
    if rereview:
        return Decision(
            "편집 반영 + 재검토 요청",
            f"rra_review 호출 ({round_no + 1}차 — 바뀐 문장·남은 의견 위주)",
            "rra_review",
        )
    return Decision("편집 반영", "rra_edit 호출 → 새 버전 저장, 재검토는 담당자가 선택", "rra_edit")


def on_finalize() -> Decision:
    return Decision(
        "담당자의 최종 마무리 (검토 1회 이상 또는 건너뜀, 검토 중 아님)",
        "rra_finalize 호출 → 선택형 확정·제안자 정보·render_check → HWPX",
        "rra_finalize",
    )


def on_reopen() -> Decision:
    return Decision("마무리된 제안서 다시 열기", "rra_reopen 호출 → editing", "rra_reopen")
