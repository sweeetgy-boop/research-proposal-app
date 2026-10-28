/** ② 유사과제 흐름(레인 A) 경로 — 응답 모양은 types-precheck.ts.
 *  v3(ADR 0039): 표 먼저(stage=rule) → AI 판정(/judgment) → 과제안(/recommendations·/more). AI 경로는 signal 을 받아
 *  [취소] 하면 fetch 를 끊는다(서버는 그 작업만 멈춘다). 응답 시간 제한 없음. */
import { request } from "./client";
import type { ComparisonFlowOut, PlanField, PolishOut, PrecheckFlowOut, PrecheckRequest } from "./types-precheck";

const V = "/v1";

/** ② 표 먼저 — 실시간 검색 + 규칙 판정까지 (judgment.status = pending) */
export const precheckFast = (req: PrecheckRequest, signal?: AbortSignal) =>
  request<PrecheckFlowOut>(`${V}/precheck?stage=rule`, { method: "POST", body: req, signal });
/** 차별성 비교표 — [유사함] 으로 고른 행만 (similar_choices) */
export const comparisonFlow = (req: PrecheckRequest, signal?: AbortSignal) =>
  request<ComparisonFlowOut>(`${V}/precheck/comparison`, { method: "POST", body: req, signal });
/** AI 같음 판정 — 표 먼저 뒤 / [다시 시도](retry) */
export const judgePrecheck = (req: PrecheckRequest, retry = false, signal?: AbortSignal) =>
  request<PrecheckFlowOut>(`${V}/precheck/judgment${retry ? "?retry=true" : ""}`, { method: "POST", body: req, signal });
/** 옛 이름 — [다시 시도] */
export const retryJudgment = (req: PrecheckRequest, signal?: AbortSignal) => judgePrecheck(req, true, signal);
/** 과제안 만들기 / [과제안 다시 만들기] — 지금 AI 판정·선택을 근거로 */
export const recommendFlow = (req: PrecheckRequest, signal?: AbortSignal) =>
  request<PrecheckFlowOut>(`${V}/precheck/recommendations`, { method: "POST", body: req, signal });
/** [차별화 과제안 더 만들기] — 이미 보인 안과 다른 안만 */
export const recommendMore = (req: PrecheckRequest, recId: string, signal?: AbortSignal) =>
  request<Pick<PrecheckFlowOut, "notice" | "recommendations">>(`${V}/precheck/recommendations/more`, {
    method: "POST",
    body: { request: req, rec_id: recId },
    signal,
  });
/** 활용·차별화 제안 — [유사함] 행만 */
export const differentiateFlow = (req: PrecheckRequest, signal?: AbortSignal) =>
  request<PrecheckFlowOut>(`${V}/precheck/differentiate`, { method: "POST", body: req, signal });
/** 선택 반영 — 차단 여부·해제·다음 버튼 사유 (LLM 없음) + 선택 기록 */
export const applyChoices = (req: PrecheckRequest, signal?: AbortSignal) =>
  request<PrecheckFlowOut>(`${V}/precheck/choices`, { method: "POST", body: req, signal });
/** 과제안 한 칸 [AI로 다듬기] */
export const polishField = (req: PrecheckRequest, field: PlanField, text: string, signal?: AbortSignal) =>
  request<PolishOut>(`${V}/precheck/plan/polish`, { method: "POST", body: { request: req, field, text }, signal });
/** 초안이 있는 run 의 비교표(제안 행 = 초안) */
export const runComparison = (runId: string) =>
  request<ComparisonFlowOut & { run_id: string }>(`${V}/runs/${encodeURIComponent(runId)}/comparison`);
