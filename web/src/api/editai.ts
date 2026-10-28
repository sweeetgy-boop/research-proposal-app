/** 작성·편집 AI 경로 (레인 B, 2026-10-28) — 정책적 중요도 작성안·보강 질문·변경 세기·보완 질문(새 필드). */
import { useQuery } from "@tanstack/react-query";
import { request } from "./client";
import type {
  ChangesOut,
  ClarifyOutV2,
  PolicyCardsIn,
  PolicyCardsOut,
  PolicyChoice,
  PolicyPolishOut,
  ProposalRequest,
  RewriteOutV2,
  SectionQuestionsOutV2,
  VersionWithStatus,
} from "./types";

const V = "/v1";
const enc = encodeURIComponent;

export const clarifyV2 = (req: ProposalRequest) => request<ClarifyOutV2>(`${V}/precheck/clarify`, { method: "POST", body: req });

// 정책 작성안·[AI로 다듬기] — 시간 제한 없음, signal 로 [취소] (서버 cancel_on_disconnect)
export const ideaPolicyCards = (body: PolicyCardsIn, signal?: AbortSignal) =>
  request<PolicyCardsOut>(`${V}/ideas/policy-cards`, { method: "POST", body, signal });
export const ideaPolicyPolish = (req: ProposalRequest, choice: PolicyChoice, text: string, signal?: AbortSignal) =>
  request<PolicyPolishOut>(`${V}/ideas/policy-cards/polish`, { method: "POST", body: { ...req, choice, text }, signal });

export const runPolicyCards = (id: string, excludeDocIds: string[] = [], signal?: AbortSignal) =>
  request<PolicyCardsOut>(`${V}/runs/${enc(id)}/policy-cards`, { method: "POST", body: { exclude_doc_ids: excludeDocIds }, signal });
export const runPolicyPolish = (id: string, choice: PolicyChoice, text: string, signal?: AbortSignal) =>
  request<PolicyPolishOut>(`${V}/runs/${enc(id)}/policy-cards/polish`, { method: "POST", body: { choice, text }, signal });
export const runPolicyChoice = (id: string, choice: PolicyChoice, baseVersion?: number | null) =>
  request<VersionWithStatus>(`${V}/runs/${enc(id)}/policy-choice`, { method: "POST", body: { choice, base_version: baseVersion ?? null } });

export const getChanges = (id: string) => request<ChangesOut>(`${V}/runs/${enc(id)}/changes`);

export const rewriteSectionV2 = (id: string, key: string, signal?: AbortSignal) =>
  request<RewriteOutV2>(`${V}/runs/${enc(id)}/sections/${enc(key)}/rewrite`, { method: "POST", signal });

export const sectionQuestionsV2 = (id: string, key: string, refresh = false, signal?: AbortSignal) =>
  request<SectionQuestionsOutV2>(`${V}/runs/${enc(id)}/sections/${enc(key)}/questions${refresh ? "?refresh=true" : ""}`, { signal });

export const editAiKeys = {
  changes: (id: string) => ["run", id, "changes"] as const,
};

/** ④ "변경 n건" 의 서버 몫 — 마지막 검토 이후 바로 저장된 변경(그림·근거·정책 근거·보완 메모…) */
export function useChanges(id: string, enabled = true) {
  return useQuery({ queryKey: editAiKeys.changes(id), queryFn: () => getChanges(id), enabled });
}
