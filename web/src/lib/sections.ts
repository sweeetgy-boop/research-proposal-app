/** 섹션 키 → 양식 칸 이름 (config/templates/proposal_korail.rules.yaml titles 와 같다). */
export const SECTION_TITLES: Record<string, string> = {
  title: "1-가 연구과제명",
  task_type: "1-다 과제유형",
  policy_importance: "2-가-(1) 정책적 중요도",
  tech_importance: "2-가-(2) 기술적 중요도",
  strategy_alignment: "2-가-(3) 공사 경영전략과의 정합성",
  objective: "2-나 연구목적",
  method: "2-다 연구 방법 및 주요내용",
  expected_management: "3-가 기대효과 (경영혁신 측면)",
  expected_technology: "3-나 기대효과 (기술혁신 측면)",
  expected_standing: "3-다 기대효과 (대외위상 측면)",
  utilization: "4 연구결과 활용계획",
  overlap_review: "5 특이사항 (유사과제 검토 결과)",
};

export const sectionTitle = (key: string): string => SECTION_TITLES[key] ?? key;

/** 선택형 섹션 (체크 칸) — 본문 대신 확정값으로 양식에 들어간다 */
export const CHOICE_SECTIONS = new Set(["task_type", "utilization", "strategy_alignment"]);

export const STEP_LABELS: Record<string, string> = {
  retrieve: "근거 검색",
  outline: "섹션 설계도",
  finalize: "규칙 검사·v1",
  draft_review: "Argon 1차 검토",
  clarify: "입력 보강",
};

export function stepLabel(name: string): string {
  if (name.startsWith("section:")) return sectionTitle(name.slice("section:".length));
  return STEP_LABELS[name] ?? name;
}

/** 문장 origin → 배지 이름. 백엔드 origin 값: llm(로컬 작성)·argon(Argon 보완)·argon_added·reviewed·proposer_edit·proposer_input·app */
export const ORIGIN_LABELS: Record<string, string> = {
  llm: "로컬 작성",
  local: "로컬 작성",
  argon: "Argon 보완",
  reviewed: "Argon 보완",
  argon_added: "Argon 추가",
  added: "Argon 추가",
  proposer_edit: "제안자 수정",
  proposer_input: "제안자 입력",
  app: "앱 규칙",
};

export const STATUS_LABELS: Record<string, string> = {
  queued: "대기 중",
  running: "생성 중",
  interrupted: "중단됨",
  failed: "실패",
  invalid: "입력 오류",
  draft_reviewing: "1차 검토 중",
  drafted: "초안 완료",
  editing: "수정 중",
  final_reviewing: "최종 검토 중",
  final_reviewed: "최종 검토 완료",
  finalized: "마무리 완료",
};

export const statusLabel = (s: string): string => STATUS_LABELS[s] ?? s;

/** 근거 수준(basis) 라벨 — domain/rules/evidence.py BASIS_LABELS 와 같다 */
export const BASIS_LABELS: Record<string, string> = {
  full_text: "원문",
  summary: "공개 요약",
  abstract: "초록",
  title: "제목",
  image_vision: "이미지 판독",
};
export const basisLabel = (b: string | null | undefined): string => (b ? BASIS_LABELS[b] ?? b : "미상");

/** Argon 근거 적합성 → 배지 색 */
export const SUPPORT_VARIANT: Record<string, "success" | "warning" | "destructive"> = {
  지지: "success",
  부분: "warning",
  불일치: "destructive",
};

/** 브리핑·비교표 건너뜀 사유 */
export const SKIP_LABELS: Record<string, string> = {
  no_evidence: "검색된 논문·보고서가 없습니다",
  parse_failed: "모델 응답을 해석하지 못했습니다",
  no_llm: "브리핑 모델이 없습니다",
};
