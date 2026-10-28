/** 레인 D(항목 21·22) 경로 — ⑤ 최종 검토 [취소]. */
import { request } from "./client";
import type { RunState } from "./types";

const V = "/v1";
const enc = encodeURIComponent;

/** 진행 중인 최종 검토(Argon)만 멈춘다 — 검토 전 상태로 돌아가고 결과·버전은 남지 않는다 */
export const cancelFinalReview = (id: string) => request<RunState>(`${V}/runs/${enc(id)}/final-review/cancel`, { method: "POST" });
