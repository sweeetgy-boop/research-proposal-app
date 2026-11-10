// 새 과제 추천 갈래 (ADR 0057, docs/contracts/novel-recommend.md) — 0단계 계약. 레인은 고치지 않는다.
// POST /v1/precheck/recommendations(·/v1/precheck stage=full 의 recommendations) 응답의 recommendations 객체가
// mode === "novel" 이면 아래 모양이다. 본문 글은 모두 외부 LLM 출력·수집 문서 제목(비신뢰).

import type { PlanRecommendations } from "./types-precheck";

export type RecommendMode = "differentiate" | "novel";
export type BarrierType = "수요" | "규제" | "비용" | "기술" | "운영";
export type BasisLevel = "근거 있음" | "추정";
export type Maturity = "즉시 적용" | "실증 필요" | "연구 필요";
export type StageName = "기획" | "시범" | "확대";

export interface NoveltyUnavailable {
  source: string;
  /** 화면 이름 (예: "NTIS") */
  label: string;
  /** 열거값: ip_blocked | timeout | error | off | no_key | rate_limited(일일 호출 한도) */
  status: string;
  /** 한국어 설명 (예: "서버 IP 등록 필요로 확인 못 함") */
  status_label: string;
}

export interface NoveltyCoverage {
  /** 실제로 확인한 자료원 코드 */
  searched: string[];
  /** 화면 이름 — searched 와 같은 순서 */
  searched_labels: string[];
  /** 실시간 검색을 실제로 했는가 */
  live: boolean;
  unavailable: NoveltyUnavailable[];
  /** "저장 자료와 실시간 검색 범위 안에서 기존 과제 없음" */
  note: string;
}

export interface Analogy {
  doc_id: string;
  title: string;
  source: string;
  source_label: string;
  /** 분야 — 자료원 메타데이터에서 (지어내지 않음) */
  domain_label: string;
  why_relevant: string;
  url: string | null;
  year: number | null;
  live: boolean;
}

/** 다른 분야 사례·관련 선행 자료 구획의 검색 범위 보고 — 문제 정의 카드를 쓴 요청에만 온다(없으면 종전 화면 그대로).
 *  heading·description·scope_text·empty_text 는 서버가 만든 문장 — 웹은 조립하지 않고 그대로 보인다. */
export interface AnalogyReport {
  /** other_field: 철도 밖 사례(종전) / related: 대상이 철도 시설이라 철도 자료 포함 */
  kind: "other_field" | "related";
  /** 화면 제목 — "다른 분야 사례" | "관련 선행 자료" */
  heading: string;
  /** 제목 아래 설명 한 줄 */
  description: string;
  count: number;
  /** 약해서 뺀 자료 수 (0 이면 표시 안 함) */
  dropped_weak: number;
  sources_total: number;
  sources_checked: number;
  /** 확인한 자료원 화면 이름 */
  checked_labels: string[];
  /** 확인 못 한 자료원 */
  unavailable: NoveltyUnavailable[];
  /** 응답하지 않은 자료원이 있다 → '없음'이 아니라 '일부만 확인' */
  partial: boolean;
  languages: string[];
  /** 검색 범위 한 줄 */
  scope_text: string;
  /** 0건일 때 보일 문장 */
  empty_text: string;
}

export interface NovelRef {
  doc_id: string;
  title: string;
  source: string;
  source_label: string;
  url: string | null;
}

export interface Barrier {
  type: BarrierType;
  statement: string;
  basis: { level: BasisLevel; doc_ids: string[] };
  /** 확인 방법 — level 이 "추정" 이면 늘 있음 */
  check: string;
}

export interface NovelTitle {
  title: string;
  /** 같은 안 barriers 의 인덱스(0부터), 1개 이상 */
  resolves: number[];
  /** resolves 순서대로 장벽 유형 — 화면 "해소: 규제·비용" 배지 */
  resolves_types: BarrierType[];
  reason: string;
  /** ADR 0065 — 이 과제명이 기댄 TRIZ 발명 원리(문제 정의 카드가 있을 때만). 없으면 빈 배열이거나 칸이 없다 */
  principles?: { number: number; name: string }[];
}

export interface NovelRecommendation {
  index: number;
  approach: string;
  summary: string;
  first_step: string;
  /** 기획 → 시범 → 확대 순 (없는 단계는 빠짐) */
  stages: { stage: StageName; text: string }[];
  maturity: Maturity;
  evidence: string[];
  /** evidence ∪ 장벽 근거 doc_id 의 제목·자료원 — 화면은 내부 번호 대신 이것을 보인다 */
  refs: NovelRef[];
  barriers: Barrier[];
  /** 해소하는 장벽 수가 많은 것 먼저 */
  titles: NovelTitle[];
}

/** 차별화 갈래 응답에 더해지는 칸 (호환 — 없으면 differentiate 로 본다) */
export interface ModeFields {
  mode?: RecommendMode;
  /** 새로움 확인에서 유사 과제가 새로 걸려 novel 을 취소하고 differentiate 로 되돌렸다 */
  novelty_reverted?: boolean;
  /** 그때 새로 걸린 행 doc_id — 같은 응답의 alerts 에 이미 들어 있다 */
  novelty_alert_ids?: string[];
}

export interface NovelRecommendations
  extends Omit<PlanRecommendations, "recommendations">,
    Omit<ModeFields, "mode"> {
  mode: "novel";
  coverage: NoveltyCoverage;
  analogies: Analogy[];
  /** 검색 범위 보고 — 없으면(카드 없는 요청) 종전 화면 그대로 */
  analogy_report?: AnalogyReport | null;
  recommendations: NovelRecommendation[];
}

export type DifferentiateRecommendations = PlanRecommendations & ModeFields;

export type AnyRecommendations = NovelRecommendations | DifferentiateRecommendations;

export function isNovel(r: AnyRecommendations | null | undefined): r is NovelRecommendations {
  return !!r && (r as { mode?: string }).mode === "novel";
}
