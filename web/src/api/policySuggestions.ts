/** 정책 근거 추천 — 다른 레인이 만드는 `POST /v1/ideas/policy-suggestions` 의 클라이언트. 모양이 바뀌면 이 파일만 고친다.
 *  아직 main 에 없을 수 있어 404/405/503 을 "미개방" 으로 돌려준다(화면은 짧은 안내만). 호출은 제안자가 버튼을 눌렀을 때만
 *  (화면을 열 때마다 4xx 를 받으면 브라우저 콘솔 오류가 남아 CSP e2e 가 깨진다). */
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

/** 서버 응답(PR #29): `{notice, count, suggestions[{doc_id,title,year,page,quote,url,policy_basis_text,…}]}`.
 *  이전 가정 모양 `{items:[{document,…}]}` 도 받아들인다. */
export interface PolicySuggestionsOut {
  notice?: string;
  count?: number;
  suggestions?: Array<{
    doc_id?: string;
    title?: string;
    year?: number | string | null;
    page?: number | string | null;
    quote?: string;
    url?: string | null;
    policy_basis_text?: string;
  }>;
  items?: PolicySuggestion[];
}

function normalizeItems(out: PolicySuggestionsOut | undefined): PolicySuggestion[] {
  const raw = Array.isArray(out?.suggestions)
    ? out.suggestions.map((s) => ({
        document: s.title ?? s.doc_id ?? "",
        year: s.year ?? null,
        page: s.page ?? null,
        quote: typeof s.policy_basis_text === "string" && s.policy_basis_text ? s.policy_basis_text : (s.quote ?? ""),
        url: s.url ?? null,
      }))
    : Array.isArray(out?.items)
      ? out.items
      : [];
  return raw.filter((i) => i && typeof i.quote === "string" && i.quote.length > 0);
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
    return { state: "ok", items: normalizeItems(out) };
  } catch (e) {
    // 404·405(경로 없음 — SPA 정적 catch-all 은 GET 만 받는다)·503(꺼짐) → 미개방
    if (isApiError(e) && (e.status === 404 || e.status === 405 || e.status === 503)) return { state: "unavailable" };
    return { state: "error", error: e };
  }
}

/** 제안자가 고른 한 건 → 정책 근거 칸에 덧붙일 문구 */
export function formatPolicyQuote(s: PolicySuggestion): string {
  const meta = [s.document, s.year ? String(s.year) : null, s.page ? `p.${s.page}` : null].filter(Boolean).join(", ");
  return meta ? `${s.quote} (${meta})` : s.quote;
}
