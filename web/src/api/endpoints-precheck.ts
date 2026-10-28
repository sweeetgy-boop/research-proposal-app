/** ② 유사과제 흐름(레인 A) 경로 — 응답 모양은 types-precheck.ts. */
import { request } from "./client";
import type { ComparisonFlowOut, PlanField, PolishOut, PrecheckFlowOut, PrecheckRequest } from "./types-precheck";

const V = "/v1";

/** 차별성 비교표 — [유사함] 으로 고른 행만 (similar_choices) */
export const comparisonFlow = (req: PrecheckRequest) =>
  request<ComparisonFlowOut>(`${V}/precheck/comparison`, { method: "POST", body: req });
/** AI 같음 판정 [다시 시도] */
export const retryJudgment = (req: PrecheckRequest) =>
  request<PrecheckFlowOut>(`${V}/precheck/judgment`, { method: "POST", body: req });
/** [과제안 다시 만들기] — 고른 [유사함] 과 겹치지 않는 안 */
export const recommendFlow = (req: PrecheckRequest) =>
  request<PrecheckFlowOut>(`${V}/precheck/recommendations`, { method: "POST", body: req });
/** 활용·차별화 제안 — [유사함] 행만 */
export const differentiateFlow = (req: PrecheckRequest) =>
  request<PrecheckFlowOut>(`${V}/precheck/differentiate`, { method: "POST", body: req });
/** 과제안 한 칸 [AI로 다듬기] */
export const polishField = (req: PrecheckRequest, field: PlanField, text: string) =>
  request<PolishOut>(`${V}/precheck/plan/polish`, { method: "POST", body: { request: req, field, text } });
/** 초안이 있는 run 의 비교표(제안 행 = 초안) */
export const runComparison = (runId: string) =>
  request<ComparisonFlowOut & { run_id: string }>(`${V}/runs/${encodeURIComponent(runId)}/comparison`);
