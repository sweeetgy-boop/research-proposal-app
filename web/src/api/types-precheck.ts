/** ② 유사과제 흐름(레인 A, 2026-10-28) 손으로 적은 API 타입 — entrypoints/views.py 를 따른다.
 *  요청 본문의 새 칸(similar_choices·method·scope·idea_versions)은 openapi.json 재생성 전이라 여기서 넓힌다. */
import type { ComparisonOut, Differentiation, OverlapAlert, PrecheckOut, ProposalRequest, Recommendation, Recommendations } from "./types";

export type SimilarChoiceValue = "similar" | "unrelated";
export interface SimilarChoice {
  doc_id: string;
  choice: SimilarChoiceValue;
}

/** 과제안 다섯 칸 — ProposalRequest 필드 이름 */
export type PlanField = "title_hint" | "goal" | "method" | "scope" | "differentiation";
export type IdeaVersionKind = "original" | "card" | "edited";
export interface IdeaVersion {
  kind: IdeaVersionKind;
  fields: Partial<Record<PlanField, string>>;
  card_index?: number | null;
  note?: string;
  at?: string;
}

/** ② 이후 들고 다니는 입력 — 서버는 ProposalRequest·RunIn 으로 읽는다(모르는 칸은 무시). */
export type PrecheckRequest = ProposalRequest & {
  method?: string;
  scope?: string;
  similar_choices?: SimilarChoice[];
  /** POST /v1/runs 의 RunIn.idea_versions — 입력에 실어 보낸다(다른 경로는 무시) */
  idea_versions?: IdeaVersion[];
};

export type SameVerdict = "same" | "partial" | "different";

export interface PrecheckAlert extends OverlapAlert {
  rerank_score?: number | null;
  rule_blocking?: boolean | null;
  judgment?: SameVerdict | null;
  judgment_label?: string | null;
  judgment_reason?: string;
  judged_by?: "argon" | "local" | "rule" | null;
  judged_by_label?: string | null;
  merged_ids?: string[];
  choice?: SimilarChoiceValue | null;
  /** ② v3 (ADR 0039) 판정 칸 — 같다→차단·일부 겹침→근접·다르다→관련 낮음. AI 판정 전엔 규칙 기준 */
  level?: JudgmentLevel;
  level_label?: string;
  level_basis?: "ai" | "rule";
  level_basis_label?: string;
  /** 관련도 — reranker 점수의 쉬운 말(높음·보통·낮음). 없으면 null */
  relevance?: "high" | "mid" | "low" | null;
  relevance_label?: string | null;
  /** 자료원 이름 (사내 과제 현황·알리오 공시 연구보고서 …) */
  source_label?: string;
}

export type JudgmentLevel = "blocking" | "near" | "low";

export interface JudgmentInfo {
  /** pending = 표 먼저 — AI 판정은 POST /v1/precheck/judgment 가 이어서 (ADR 0039) */
  status: "ai" | "rule_fallback" | "off" | "no_candidates" | "pending";
  judged_by: string | null;
  judged_by_label: string | null;
  message: string;
  retry_available: boolean;
  candidates: number;
  provider: string | null;
  model: string | null;
  calls: number;
}

export interface PlanRecommendationRef {
  doc_id: string;
  title: string;
  source_label: string;
}

export interface PlanRecommendation extends Recommendation {
  goal?: string;
  method?: string;
  scope?: string;
  /** 근거 과제·자료 — 제목·자료원 (화면에 내부 번호를 보이지 않는다) */
  refs?: PlanRecommendationRef[];
  /** 카드 겹침 재판정 (ADR 0039) — "같다" 로 판정된 가까운 과제 제목 1~2건과 한 줄 겹치는 점 */
  overlap_titles?: string[];
  overlap_reason?: string;
  overlap_by?: "argon" | "local" | "rule" | null;
  overlap_by_label?: string | null;
  /** 겹쳐서 겹치는 부분을 피해 한 번 다시 받은 안 */
  regenerated?: boolean;
  /** 차별성 판단 (판단) */
  difference?: "high" | "mid" | "low" | null;
  difference_label?: string | null;
  /** [더 만들기] 로 보탠 안 */
  added?: boolean;
}

export interface PlanRecommendations extends Omit<Recommendations, "recommendations" | "discarded"> {
  recommendations: PlanRecommendation[];
  discarded: { title?: string; reason?: string; reason_label?: string }[];
  skipped_label?: string | null;
  regenerated?: boolean;
  similar_doc_ids?: string[];
  overlap_checked?: boolean;
  overlap_regenerated?: number;
  /** POST /v1/precheck/recommendations/more — 이번에 보탠 수와 0건이면 사유 */
  added?: number;
  added_reason?: string | null;
}

export interface PlanDifferentiation extends Differentiation {
  skipped_label?: string | null;
}

export interface PrecheckFlowOut extends Omit<PrecheckOut, "alerts" | "recommendations" | "differentiation"> {
  alerts: PrecheckAlert[];
  recommendations?: PlanRecommendations;
  differentiation?: PlanDifferentiation;
  judgment?: JudgmentInfo;
  core_keywords?: string[];
  keyword_origin?: string;
  released?: boolean;
  released_note?: string | null;
  gate_reason?: string | null;
  similar_count?: number;
  llm_budget_exhausted?: boolean;
  /** AI 가 "다르다" 로 본 행 — 선택이 없는 행에만 [관련 없음] 을 미리 고른다 */
  default_choices?: SimilarChoice[];
}

export interface ComparisonFlow {
  aspects: { key: string; label: string }[];
  proposal: ComparisonOut["comparison"]["proposal"];
  projects: ComparisonOut["comparison"]["projects"];
  empty_reason?: string | null;
  proposal_source?: "input" | "draft";
  extraction?: "ai" | "rule";
  extraction_by?: string | null;
  extraction_label?: string;
}

export interface ComparisonFlowOut {
  notice: string;
  comparison: ComparisonFlow;
}

/** POST /v1/precheck/plan/polish */
export interface PolishOut {
  notice: string;
  field: PlanField;
  text: string;
  changed: boolean;
  by: string | null;
  by_label: string | null;
  reason: string | null;
}

export const PLAN_FIELDS: { key: PlanField; label: string; short?: boolean }[] = [
  { key: "title_hint", label: "과제명(가제)", short: true },
  { key: "goal", label: "연구목표" },
  { key: "method", label: "연구방법" },
  { key: "scope", label: "적용범위", short: true },
  { key: "differentiation", label: "기존 과제 대비 차이" },
];
