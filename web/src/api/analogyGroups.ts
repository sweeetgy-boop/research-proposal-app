/** 유추 자료 묶음 비교 분석 (ADR 0065 덧붙임, docs/contracts/problem-card.md 4.6절) — ② 새 과제안 갈래의
 *  '비슷한 자료' 묶음 하나를 AI 로 비교한다. 목록이 그려진 뒤 뒤에서 부르고, 실패해도 화면은 묶음만 보인다
 *  (오류를 삼키는 일은 부르는 쪽 AnalogyGroup 이 한다). 응답 모양은 types-novel.ts. */
import { request } from "./client";
import type { Analogy, AnalogyGroupAnalysis } from "./types-novel";
import type { PrecheckRequest } from "./types-precheck";

export const ANALOGY_GROUP_PATH = "/v1/precheck/analogy-groups/analyze";
/** 서버가 상한을 주지 않았을 때 한 화면에서 분석할 묶음 수 */
export const DEFAULT_GROUP_ANALYZE_MAX = 2;
/** 근거 규칙이 바꿔 넣는 문구 — 이 글이 든 칸 옆에 [원문 보기] */
export const NEEDS_SOURCE_TEXT = "초록으로는 구분 안 됨 — 원문 확인 필요";

/** 묶음 하나(대표 + 비슷한 자료, 2~5건) 비교 분석. signal 로 끊으면 서버도 그 작업을 멈춘다 */
export const analyzeAnalogyGroup = (req: PrecheckRequest, docIds: string[], opts: { signal?: AbortSignal } = {}) =>
  request<AnalogyGroupAnalysis>(ANALOGY_GROUP_PATH, { method: "POST", body: { request: req, doc_ids: docIds }, signal: opts.signal });

/** 묶음인가 — 비슷한 자료가 1건 이상 붙어 있다 */
export const isGroup = (a: Analogy): boolean => (a.similar?.length ?? 0) > 0;

/** 분석 요청에 보낼 문서(대표 + 비슷한 자료) — 서버 상한 5건 */
export const groupDocIds = (a: Analogy): string[] => [a.doc_id, ...(a.similar ?? []).map((m) => m.doc_id)].slice(0, 5);
