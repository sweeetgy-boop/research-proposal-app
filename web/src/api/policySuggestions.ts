/** 정책 근거 추천 — 다른 레인이 만드는 `POST /v1/ideas/policy-suggestions` 의 클라이언트. 모양이 바뀌면 이 파일만 고친다.
 *  아직 main 에 없을 수 있어 404/503 을 "미개방" 으로 돌려준다(화면은 짧은 안내만). */
import { isApiError } from "./client";
import { request } from "./client";
import type { ProposalRequest } from "./types";

export interface PolicySuggestion {
  document: string;
  year: number | string | null;
  page: number | string | null;
  quote: string;
  url: string | null;
}

export interface PolicySuggestionsOut {
  notice?: string;
  items: PolicySuggestion[];
}

export type PolicyProbe = { state: "ok"; items: PolicySuggestion[] } | { state: "unavailable" } | { state: "error"; error: unknown };

/** 요청 본문: 지금의 입력(필수 4칸 + 선택 칸). 서버가 다른 모양을 받으면 여기만 바꾼다. */
export function policySuggestionBody(req: ProposalRequest): Record<string, unknown> {
  return {
    current_state: req.current_state,
    root_cause: req.root_cause,
    limitation: req.limitation,
    goal: req.goal,
    title_hint: req.title_hint ?? "",
    policy_basis: req.policy_basis ?? "",
  };
}

export async function fetchPolicySuggestions(req: ProposalRequest): Promise<PolicyProbe> {
  try {
    const out = await request<PolicySuggestionsOut>("/v1/ideas/policy-suggestions", { method: "POST", body: policySuggestionBody(req) });
    const items = Array.isArray(out?.items) ? out.items.filter((i) => i && typeof i.quote === "string") : [];
    return { state: "ok", items };
  } catch (e) {
    if (isApiError(e) && (e.status === 404 || e.status === 503)) return { state: "unavailable" };
    return { state: "error", error: e };
  }
}

/** 제안자가 고른 한 건 → 정책 근거 칸에 덧붙일 문구 */
export function formatPolicyQuote(s: PolicySuggestion): string {
  const meta = [s.document, s.year ? String(s.year) : null, s.page ? `p.${s.page}` : null].filter(Boolean).join(", ");
  return meta ? `${s.quote} (${meta})` : s.quote;
}
