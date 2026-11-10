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
  policy_basis_needed: "정책 근거 확인 필요",
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
  mode_changed: "선택이 바뀌어 과제안을 다시 받습니다",
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

/** 비교표 열 종류 → 구분 칸 이름 (ADR 0053). 응답에 kind 가 없으면(옛 서버) 유사과제다. */
export const COMPARISON_KIND_LABELS: Record<string, string> = {
  similar: "유사과제",
  reference: "선행연구",
};

export function comparisonKindLabel(kind: string | null | undefined): string {
  return COMPARISON_KIND_LABELS[kind ?? "similar"] ?? "유사과제";
}

/** 참고 논문 열의 관련 순위 (서버 relevance_rank·relevance_total) → "관련 순위 2/5".
 *  ② 관련 연구 목록(제안자가 본 순서) 안의 자리 n/총수다 (2026-11-04 소유자 결정 — 옛 "검색 관련도 높음·중간·낮음" 대신).
 *  목록 밖·옛 서버(값 없음)·말이 안 되는 값(1 미만, 순위 > 총수, 정수 아님)이면 null (표시 없음). 점수 숫자는 보이지 않는다 (ADR 0039) */
export function referenceRankLabel(rank: number | null | undefined, total: number | null | undefined): string | null {
  if (rank == null || total == null) return null;
  if (!Number.isInteger(rank) || !Number.isInteger(total) || rank < 1 || rank > total) return null;
  return `관련 순위 ${rank}/${total}`;
}

/** Argon(Gemini) 연결 상태 알림 띠 (ADR 0055) — /healthz `llm.gemini` 열거값 → 화면 문구.
 *  ok·unknown(기록 없음)·모르는 값이면 띠를 내지 않는다. 사유 줄은 관리자에게만. 코드는 화면에 내지 않는다. */
export const ARGON_DOWN_TITLE = "AI(Argon) 연결 오류 — 로컬 모델로 대체 중";
export const ARGON_REASON_LABELS: Record<string, string> = {
  key_invalid: "API 키 확인 필요",
  quota: "사용 한도 초과",
  unavailable: "응답 없음",
};

/** 띠를 낼 상태면 사유 문구, 아니면 null */
export function argonDownReason(state: string | null | undefined): string | null {
  return (state && ARGON_REASON_LABELS[state]) || null;
}

/** 운영 상태 띠 (계약 docs/contracts/healthz-status.md, 레인 C) — /healthz `tunnel`·`llm.local` 열거값 → 관리자에게만 보이는
 *  한 줄. ok·unknown(기록 없음)·모르는 값이면 줄을 내지 않는다. 내부 코드(down·unavailable)는 화면에 내지 않는다. */
export const OPS_TUNNEL_DOWN = "외부 접속 경로(Funnel) 내려감";
export const OPS_LOCAL_LLM_DOWN = "로컬 모델 응답 없음";
export function opsAlertLines(ops: { tunnel?: string | null; local?: string | null } | null | undefined): string[] {
  const lines: string[] = [];
  if (ops?.tunnel === "down") lines.push(OPS_TUNNEL_DOWN);
  if (ops?.local === "unavailable") lines.push(OPS_LOCAL_LLM_DOWN);
  return lines;
}

/** provider 이름 → 화면 이름 */
export function providerLabel(provider: string | null | undefined): string {
  if (provider === "gemini") return "Argon";
  if (provider === "mlx" || provider === "local") return "로컬 모델";
  return "외부 모델";
}

/** ① '핵심 문제' 카드 (ADR 0065, docs/contracts/problem-card.md 5절) — 화면 문구는 여기 한 곳.
 *  카드의 열거값(신호·확인 경로·확인 필요 사유·방법 이름)은 화면에 내보내지 않는다. 문제 성격·켜진 신호는 1차에 기록만 — 화면 문구가 없다. */
export const CARD_TITLE = "핵심 문제";
export const CARD_INTRO = "입력을 AI 가 한 번 정리한 내용입니다. 맞으면 그대로 다음으로, 틀리면 그 줄을 고치십시오.";
export const CARD_PENDING = "문제 정리 중…";
export const CARD_INPUT_CHANGED = "입력이 바뀌었습니다 — 다시 정리하는 중";
export const CARD_INPUT_INCOMPLETE = "입력이 바뀌었습니다 — 네 칸을 모두 채우면 다시 정리합니다";
export const CARD_EDIT_FAILED = "고친 내용을 반영하지 못했습니다. 잠시 뒤 다시 [적용] 하십시오.";
export const CARD_EMPTY = "(비어 있음)";
export const CARD_EXPERT_SUMMARY = "전문가 분석 펼치기";
export const CARD_LINE_LABELS = {
  function: "기능 문장",
  cause: "원인",
  contradiction: "모순",
  codes: "분류",
} as const;
export const CARD_BADGES = {
  stated: "근거 있음",
  guessed: "추정",
  needsCheck: "확인 필요",
  unverified: "확인 못 함",
  user: "직접 고침",
} as const;
export const CARD_FACET_LABELS = {
  phenomenon: "현상",
  target: "대상",
  place: "장소",
  cause: "원인",
  harm: "피해",
  desired: "원하는 결과",
} as const;
export const CARD_CODE_KIND_LABELS = {
  ipc: "특허 분류(IPC)",
  science_class: "과학기술 분류",
} as const;
export const CARD_EXPERT_LABELS = {
  facets: "항목 나누기",
  ladder: "추상화 사다리",
  functionEn: "영문 기능 문장",
  causes: "근본 원인 (2단계)",
  principles: "발명 원리",
} as const;
/** 발명 원리 표시 — "1. 분할" */
export function principleLabel(p: { number: number; name: string }): string {
  return p.name ? `${p.number}. ${p.name}` : `${p.number}`;
}
/** ② 과제안 — 카드를 고친 뒤 (자동으로 다시 만들지 않는다) */
export const PLANS_STALE_NOTE = "문제 정의가 바뀌었습니다.";
export const PLANS_REGENERATE = "과제안 다시 만들기";
