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
from rra.domain.rules.differentiation import needs_differentiation

Tool = Literal[
    "rra_precheck",
    "rra_clarify",
    "rra_differentiate",
    "rra_recommend",
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
    recommend_auto: bool = True,
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
    if has_blocking(alerts):  # 기획서 기능 2 — 차단 알림이면 차별화 제안을 자동 실행
        out.append(on_differentiate())
    elif needs_differentiation(alerts):  # 근접(임계치 90% 이상)만이면 담당자가 요청할 때
        out.append(on_differentiate_on_request())
    out.append(on_recommend(auto=recommend_auto))  # 차별화 과제 추천 (ADR 0012)
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


def on_differentiate() -> Decision:
    return Decision(
        "차단 알림 있음",
        "rra_differentiate 자동 호출 → 겹친 과제별 활용·차별화 방향 제안 (담당자가 고르거나 고침)",
        "rra_differentiate",
    )


def on_differentiate_on_request() -> Decision:
    return Decision(
        "근접(임계치의 90% 이상) 알림만 있음",
        "담당자가 [차별화 제안 받기]를 누르면 rra_differentiate 호출",
        "rra_differentiate",
        needs_human=True,
    )


def on_recommend(*, auto: bool = True) -> Decision:
    """precheck 완료 → 차별화 과제 추천(0~5건). 자동 1회(recommend.auto), 다시 받기는 요청 시."""
    if auto:
        return Decision(
            "precheck 완료",
            "rra_recommend 자동 호출(1회) → 기존 과제와 차별성을 갖는 과제 0~5건과 이유 표시",
            "rra_recommend",
        )
    return on_recommend_on_request()


def on_recommend_on_request() -> Decision:
    return Decision(
        "사용자가 [추천 다시 받기] 요청",
        "rra_recommend 호출 → 추천 카드 갱신 (자동 재실행 없음)",
        "rra_recommend",
        needs_human=True,
    )


def on_query() -> Decision:
    return Decision(
        "담당자의 자료 질의", "rra_search 호출 → 출처 id 와 함께 근거 구간 제시", "rra_search"
    )


def on_confirm() -> Decision:
    return Decision("담당자의 선택형 항목 확정", "rra_confirm 호출 → 확정값 저장", "rra_confirm")


# ── ③ 초안 생성(로컬 작성 + Argon 1차 검토) → ④ 직접 수정 → ⑤ 최종 검토 → ⑥ 마무리 (ADR 0011) ──
def on_clarify(*, questions: int) -> Decision:
    """③ 시작 전 입력 보강 질문(Q1). 질문이 0개면 바로 생성."""
    if questions <= 0:
        return Decision(
            "보강 질문 없음 (입력 충분)", "바로 초안 생성(rra_generate)", "rra_generate"
        )
    return Decision(
        f"보강 질문 {questions}개 필요",
        "rra_clarify 호출 → 제안자가 답하거나 건너뛴 뒤 초안 생성",
        "rra_clarify",
        needs_human=True,
    )


def after_draft_done(*, review_available: bool, auto: bool = True) -> Decision:
    """로컬 작성 완료(v1) 뒤. 검토 LLM 이 있으면 Argon 1차 검토(draft_review, 자동) → 검증 통과분
    반영 v2, 없으면 건너뜀 기록(review_skipped) → v1 로 ④ 진행."""
    if not review_available:
        return Decision(
            "로컬 작성 완료 + review 사용 불가(키 없음 등)",
            "1차 검토를 건너뛰고 review_skipped 기록 → v1 로 직접 수정 단계",
        )
    if auto:
        return Decision(
            "로컬 작성 완료 + review 사용 가능",
            "rra_review 호출 (draft_review 1차, 자동) → 검증 통과 수정안·추가 문장 자동 반영 → v2",
            "rra_review",
        )
    return Decision(
        "로컬 작성 완료 + review 사용 가능 (자동 검토 꺼짐)",
        "담당자가 1차 검토 시작을 선택하면 rra_review 호출",
        "rra_review",
        needs_human=True,
    )


def on_edit(*, rereview: bool = False, round_no: int = 1) -> Decision:
    """④ 편집·저장. 외부 LLM 을 부르지 않는다 — 검토는 ⑤ 에서 제안자가 요청할 때만."""
    if rereview:
        return on_final_review(stale=True)
    return Decision("제안자 편집·저장", "rra_edit 호출 → 새 버전 저장 (외부 LLM 없음)", "rra_edit")


def on_final_review(*, stale: bool = False) -> Decision:
    """⑤ 제안자가 최종 검토를 요청 — 최신 저장 버전으로 1회. 이후 수정이 있어도 강제 아님."""
    return Decision(
        "제안자 최종 검토 요청" + (" (최종 검토 이후 수정 있음 — 다시 받기)" if stale else ""),
        "rra_review 호출 (final_review) → 점수·의견·수정안, 제안자가 문장별로 반영 후 저장",
        "rra_review",
        needs_human=True,
    )


def on_finalize() -> Decision:
    return Decision(
        "담당자의 최종 마무리 (최종 검토 완료 또는 건너뜀, 검토 중 아님, 임시 편집 없음)",
        "rra_finalize 호출 → 선택형 확정·제안자 정보·render_check → HWPX",
        "rra_finalize",
    )


def on_reopen() -> Decision:
    return Decision("마무리된 제안서 다시 열기", "rra_reopen 호출 → editing", "rra_reopen")
