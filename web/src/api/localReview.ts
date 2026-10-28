/** L2 로컬 2차 검토 (ADR 0040) — GET/POST /v1/runs/{id}/local-review… */
import { request } from "./client";
import type { LocalReviewOut, VersionWithStatus } from "./types";

const enc = encodeURIComponent;

export const getLocalReview = (id: string) => request<LocalReviewOut>(`/v1/runs/${enc(id)}/local-review`);

/** [반영] — 보통 편집 경로로 새 버전 */
export const applyLocalSuggestion = (id: string, suggestionId: string, baseVersion: number | null) =>
  request<VersionWithStatus>(`/v1/runs/${enc(id)}/local-review/${enc(suggestionId)}/apply`, { method: "POST", body: { base_version: baseVersion } });

/** [무시] — 결정 기록만 (새 버전 없음) */
export const dismissLocalSuggestion = (id: string, suggestionId: string) =>
  request<LocalReviewOut>(`/v1/runs/${enc(id)}/local-review/${enc(suggestionId)}/dismiss`, { method: "POST" });

/** 제안 다시 받기 (Argon) — 시간 제한 없음, signal 로 [취소] */
export const retryLocalSuggestion = (id: string, suggestionId: string, signal?: AbortSignal) =>
  request<LocalReviewOut>(`/v1/runs/${enc(id)}/local-review/${enc(suggestionId)}/retry`, { method: "POST", signal });
