/** 레인 C (ADR 0045) — ③ 작성 중 섹션 먼저 보기. */
import { request } from "./client";
import type { SectionsProgress } from "./types";

const V = "/v1";
const enc = encodeURIComponent;

/** 끝난 섹션 글(읽기 전용, 버전 아님)·남은 섹션 키 */
export const getSectionsProgress = (id: string, signal?: AbortSignal) =>
  request<SectionsProgress>(`${V}/runs/${enc(id)}/sections-progress`, { signal });
