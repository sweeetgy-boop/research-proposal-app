/** 화면에 보이는 코드 → 한국어 설명 (항목 16). 원본은 백엔드 src/rra/domain/rules/problem_labels.py —
 *  이 파일은 그 표를 그대로 옮긴 것이고 tests/domain/test_format_ui_rules.py 가 두 표가 같은지 검사한다.
 *  응답에 `label`·`severity_label`·`draft_review_skipped_label` 이 오면 그것을 먼저 쓴다.
 *  코드를 그대로 화면에 내지 않는다 — 모르는 코드는 UNKNOWN_PROBLEM. */

export const PROBLEM_LABELS: Record<string, string> = {
  missing: "필수 섹션이 비어 있음",
  too_long: "칸 글자 수 초과",
  no_choice: "선택형 항목을 고르지 못함",
  no_evidence: "근거가 없는 문장",
  evidence_forbidden: "근거를 달지 않는 섹션에 근거가 붙음",
  input_missing: "입력이 비어 작성하지 않은 섹션",
  catalog_empty: "선택지 목록이 비어 작성하지 않은 섹션",
  no_relevant_evidence: "관련 자료가 없어 비워 둔 섹션",
  unsupported_number: "근거에 없는 수치",
  foreign_script: "한자·가나가 섞인 문장",
  long_sentence: "너무 긴 문장",
  mixed_style: "문체가 섞인 문장",
  period_mismatch: "연차 계획과 연구 기간이 맞지 않음",
  duplicate_sentence: "같은 문장이 반복됨",
  section_trimmed: "칸 길이를 넘어 뒤 문장을 뺌",
  evidence_mismatch: "검토 판정: 근거가 문장을 뒷받침하지 않음",
  evidence_all_excluded: "근거를 모두 제외한 문장",
  local_evidence_mismatch: "로컬 대조: 근거와 문장이 맞지 않음",
  generation_failed: "작성하지 못한 섹션",
  schedule_exceeds_period: "일정이 연구 기간을 넘음",
  figure_schedule_exceeds_period: "그림 일정이 연구 기간을 넘음",
};
export const UNKNOWN_PROBLEM = "확인이 필요한 알림";

export const SEVERITY_LABELS: Record<string, string> = {
  error: "오류",
  warning: "주의",
  info: "참고",
};

export const REVIEW_SKIP_LABELS: Record<string, string> = {
  no_review_llm: "1차 검토 생략(검토 모델 없음)",
  budget: "1차 검토 생략(오늘 호출 상한)",
  disabled: "1차 검토 생략(설정에서 끔)",
  failed: "1차 검토 실패(초안 그대로)",
  self_review: "1차 검토 생략(같은 모델 작성)",
};

export const STEP_LABELS: Record<string, string> = {
  retrieve: "근거 검색",
  outline: "섹션 설계도",
  sections: "섹션 작성",
  sections_sum: "섹션별 작성 시간 합계",
  finalize: "규칙 검사·첫 버전 저장",
  draft_review: "Argon 1차 검토",
  figures: "그림 만들기",
  clarify: "입력 보강",
  live_search: "실시간 자료 검색",
};

/** 응답의 label 이 있으면 그것, 없으면 표, 그것도 없으면 일반 문구 (코드는 내보내지 않는다) */
export function problemLabel(p: { code: string; label?: string | null }): string {
  return p.label || PROBLEM_LABELS[p.code] || UNKNOWN_PROBLEM;
}

export function severityLabel(p: { severity?: string | null; severity_label?: string | null }): string {
  return p.severity_label || SEVERITY_LABELS[p.severity ?? "error"] || "주의";
}

export function reviewSkipLabel(reason: string | null | undefined, label?: string | null): string | null {
  if (!reason) return null;
  return label || REVIEW_SKIP_LABELS[reason] || "1차 검토 생략";
}

export function stepKeyLabel(key: string): string | null {
  return STEP_LABELS[key] ?? null;
}

/** 작성·검토·추천을 건너뛰거나 실패한 사유 코드 → 한국어 (화면 표시용, 모르는 코드는 일반 문구) */
const REASON_LABELS: Record<string, string> = {
  fence: "응답 형식 오류",
  json: "응답 형식 오류",
  schema: "응답 형식 오류",
  invalid: "응답 형식 오류",
  choices_only: "본문 없이 선택값만 옴",
  empty: "빈 응답",
  dropped: "근거 검증에서 모두 빠짐",
  error: "모델 호출 오류",
  rate_limit: "호출 한도 초과",
  budget: "오늘 호출 상한",
  parse_failed: "모델 응답을 해석하지 못함",
  no_llm: "모델 없음",
  no_review_llm: "검토 모델 없음",
  no_candidates: "비교할 기존 과제 없음",
  no_evidence: "검색된 자료 없음",
  disabled: "설정에서 끔",
  failed: "실패",
  self_review: "같은 모델 작성",
};

export function reasonLabel(reason: string | null | undefined): string {
  if (!reason) return "사유 없음";
  return REASON_LABELS[reason] ?? "기타 사유";
}

/** provider 이름 → 화면 이름 */
export function providerLabel(provider: string | null | undefined): string {
  if (provider === "gemini") return "Argon";
  if (provider === "mlx" || provider === "local") return "로컬 모델";
  return "외부 모델";
}
