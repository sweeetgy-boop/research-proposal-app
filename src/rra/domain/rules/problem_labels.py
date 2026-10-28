"""화면에 보이는 코드 → 한국어 설명 (항목 16) — 한 곳에서 관리한다.

알림 코드(LintProblem.code)·심각도·1차 검토 생략 사유·단계 이름은 API 응답에 `label` 로 실려
화면에 간다. 웹의 `web/src/lib/labels.ts` 는 이 표를 그대로 옮긴 것이고, tests/domain/
test_problem_labels.py 가 두 표가 같은지·백엔드가 내는 모든 알림 코드에 설명이 있는지 검사한다.
코드를 새로 만들면 여기에 설명을 더한다 (없으면 테스트가 실패한다).
"""

from __future__ import annotations

# 알림 코드 — domain/rules/lint.py·style.py·evidence.py·writer.py·schedule.py·draft_failures.py
PROBLEM_LABELS: dict[str, str] = {
    "missing": "필수 섹션이 비어 있음",
    "too_long": "칸 글자 수 초과",
    "no_choice": "선택형 항목을 고르지 못함",
    "no_evidence": "근거가 없는 문장",
    "evidence_forbidden": "근거를 달지 않는 섹션에 근거가 붙음",
    "input_missing": "입력이 비어 작성하지 않은 섹션",
    "policy_basis_needed": "정책 근거 확인 필요",
    "catalog_empty": "선택지 목록이 비어 작성하지 않은 섹션",
    "no_relevant_evidence": "관련 자료가 없어 비워 둔 섹션",
    "unsupported_number": "근거에 없는 수치",
    "foreign_script": "한자·가나가 섞인 문장",
    "long_sentence": "너무 긴 문장",
    "mixed_style": "문체가 섞인 문장",
    "period_mismatch": "연차 계획과 연구 기간이 맞지 않음",
    "duplicate_sentence": "같은 문장이 반복됨",
    "section_trimmed": "칸 길이를 넘어 뒤 문장을 뺌",
    "evidence_mismatch": "검토 판정: 근거가 문장을 뒷받침하지 않음",
    "evidence_all_excluded": "근거를 모두 제외한 문장",
    "local_evidence_mismatch": "로컬 대조: 근거와 문장이 맞지 않음",
    "generation_failed": "작성하지 못한 섹션",
    "schedule_exceeds_period": "일정이 연구 기간을 넘음",
    "figure_schedule_exceeds_period": "그림 일정이 연구 기간을 넘음",
}
UNKNOWN_PROBLEM = "확인이 필요한 알림"

SEVERITY_LABELS: dict[str, str] = {"error": "오류", "warning": "주의", "info": "참고"}

# ③ 1차 검토를 돌리지 않은 이유 (RunState.draft_review_skipped)
REVIEW_SKIP_LABELS: dict[str, str] = {
    "no_review_llm": "1차 검토 생략(검토 모델 없음)",
    "budget": "1차 검토 생략(오늘 호출 상한)",
    "disabled": "1차 검토 생략(설정에서 끔)",
    "failed": "1차 검토 실패(초안 그대로)",
    "self_review": "1차 검토 생략(같은 모델 작성)",
}

# 진행·사용 기록의 단계 이름 (StepRecord.name·UsageRecord.step_seconds 키)
STEP_LABELS: dict[str, str] = {
    "retrieve": "근거 검색",
    "outline": "섹션 설계도",
    "sections": "섹션 작성",
    "sections_sum": "섹션별 작성 시간 합계",
    "finalize": "규칙 검사·첫 버전 저장",
    "draft_review": "Argon 1차 검토",
    "figures": "그림 만들기",
    "clarify": "입력 보강",
    "live_search": "실시간 자료 검색",
}


# run 상태 (RunState.status) — 웹 lib/sections.ts STATUS_LABELS 와 같다
STATUS_LABELS: dict[str, str] = {
    "queued": "대기 중",
    "running": "생성 중",
    "interrupted": "중단됨",
    "failed": "실패",
    "invalid": "입력 오류",
    "draft_reviewing": "1차 검토 중",
    "drafted": "초안 완료",
    "editing": "수정 중",
    "final_reviewing": "최종 검토 중",
    "final_reviewed": "최종 검토 완료",
    "finalized": "마무리 완료",
}


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, "진행 중")


def problem_label(code: str) -> str:
    return PROBLEM_LABELS.get(code, UNKNOWN_PROBLEM)


def severity_label(severity: str | None) -> str:
    return SEVERITY_LABELS.get(severity or "error", "주의")


def review_skip_label(reason: str | None) -> str | None:
    if not reason:
        return None
    return REVIEW_SKIP_LABELS.get(reason, "1차 검토 생략")


def step_label(name: str) -> str:
    return STEP_LABELS.get(name, name)
