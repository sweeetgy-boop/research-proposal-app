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
}

export interface JudgmentInfo {
  status: "ai" | "rule_fallback" | "off" | "no_candidates";
  judged_by: string | null;
  judged_by_label: string | null;
  message: string;
  retry_available: boolean;
  candidates: number;
  provider: string | null;
  model: string | null;
  calls: number;
}

export interface PlanRecommendation extends Recommendation {
  goal?: string;
  method?: string;
  scope?: string;
}

export interface PlanRecommendations extends Omit<Recommendations, "recommendations" | "discarded"> {
  recommendations: PlanRecommendation[];
  discarded: { title?: string; reason?: string; reason_label?: string }[];
  skipped_label?: string | null;
  regenerated?: boolean;
  similar_doc_ids?: string[];
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
