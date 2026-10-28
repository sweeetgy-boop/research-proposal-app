import { request, isApiError } from "./client";
import type { ProposalRequest } from "./types";

/** ① 정책 근거 추천 — POST /v1/ideas/policy-suggestions (2026-10-28 레인 B, ADR 0040).
 *  정책적 중요도 작성안과 같은 자료원·관련도 규칙: 국토부 계획·공사 경영목표·전략·감사 지적·정부 R&D 공고만.
 *  사전정보공표 연구용역(사내 발주)·행정 공시·사업 현황은 나오지 않는다. 인용은 URL·글머리를 뗀 통문장(서버). */

export interface PolicySuggestion {
  doc_id: string;
  document: string;
  /** 자료원 이름(한국어) — 화면은 doc_id 를 보이지 않는다 */
  source: string;
  source_label: string;
  year: number | string | null;
  page: number | string | null;
  /** 원문 그대로의 한 문장 (URL 없음) */
  quote: string;
  /** 인용 아래 "원문" 링크 */
  url: string | null;
}

/** 서버 응답: `{notice, count, suggestions[{doc_id,title,source,source_label,year,page,quote,url,policy_basis_text,…}]}`.
 *  이전 가정 모양 `{items:[{document,…}]}` 도 받아들인다. */
export interface PolicySuggestionsOut {
  notice?: string;
  count?: number;
  suggestions?: Array<{
    doc_id?: string;
    title?: string;
    source?: string;
    source_label?: string;
    year?: number | string | null;
    page?: number | string | null;
    quote?: string;
    url?: string | null;
    policy_basis_text?: string;
  }>;
  items?: Array<Partial<PolicySuggestion>>;
}

function normalizeItems(out: PolicySuggestionsOut | undefined): PolicySuggestion[] {
  const raw: Array<Partial<PolicySuggestion>> = Array.isArray(out?.suggestions)
    ? out.suggestions.map((s) => ({
        doc_id: s.doc_id ?? "",
        document: s.title ?? "",
        source: s.source ?? "",
        source_label: s.source_label ?? "",
        year: s.year ?? null,
        page: s.page ?? null,
        quote: s.quote ?? "",
        url: s.url ?? null,
      }))
    : Array.isArray(out?.items)
      ? out.items
      : [];
  return raw
    .filter((i) => i && typeof i.quote === "string" && i.quote.length > 0)
    .map((i) => ({
      doc_id: i.doc_id ?? "",
      document: i.document ?? "",
      source: i.source ?? "",
      source_label: i.source_label ?? "",
      year: i.year ?? null,
      page: i.page ?? null,
      quote: i.quote ?? "",
      url: i.url ?? null,
    }));
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

/** signal: [취소] — 서버는 연결이 끊기면 그 검색만 멈춘다. 시간 제한 없음. */
export async function fetchPolicySuggestions(req: ProposalRequest, signal?: AbortSignal): Promise<PolicyProbe> {
  try {
    const out = await request<PolicySuggestionsOut>("/v1/ideas/policy-suggestions", { method: "POST", body: policySuggestionBody(req), signal });
    return { state: "ok", items: normalizeItems(out) };
  } catch (e) {
    if (signal?.aborted) throw e; // 취소는 화면이 처리 (이전 상태 그대로)
    // 404·405(경로 없음 — SPA 정적 catch-all 은 GET 만 받는다)·503(꺼짐) → 미개방
    if (isApiError(e) && (e.status === 404 || e.status === 405 || e.status === 503)) return { state: "unavailable" };
    return { state: "error", error: e };
  }
}

/** 제안자가 고른 한 건 → 정책 근거 칸에 덧붙일 문구 (긴 URL 은 넣지 않는다 — 원문 링크는 화면 아래) */
export function formatPolicyQuote(s: Pick<PolicySuggestion, "quote" | "document" | "year" | "page">): string {
  const meta = [s.document, s.year ? String(s.year) : null, s.page ? `${s.page}` : null].filter(Boolean).join(", ");
  return meta ? `“${s.quote}” (${meta})` : `“${s.quote}”`;
}
