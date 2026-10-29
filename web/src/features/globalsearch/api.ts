/** 문서 단위 검색 GET /v1/search/docs (2026-10-29 [UI] 레인 3) — 위쪽 통합 검색 "자료" 묶음·자료 검색 화면.
 *  서버: src/rra/entrypoints/api/search_routes.py. 공용 계정은 서버가 internal 을 뺀다.
 *  doc_id 는 키로만 쓰고 화면에 보이지 않는다(제목·자료원 이름·연도만). */
import { useQuery } from "@tanstack/react-query";
import { request } from "@/api/client";
import type { DocRefData } from "@/lib/docRefs";

export interface DocHit extends DocRefData {
  doc_id: string;
  title: string;
  source: string;
  source_label: string;
  url: string | null;
  year: number | null;
  summary: string | null;
  basis: string | null;
  live: boolean;
}

export interface DocSearchOut {
  notice: string;
  docs: DocHit[];
}

export interface DocSearchParams {
  q: string;
  limit?: number;
  sources?: string[];
  yearFrom?: number | null;
  yearTo?: number | null;
}

export function docSearchPath(p: DocSearchParams): string {
  const qs = new URLSearchParams({ q: p.q.trim(), limit: String(p.limit ?? 5) });
  if (p.sources && p.sources.length > 0) qs.set("sources", p.sources.join(","));
  if (p.yearFrom) qs.set("year_from", String(p.yearFrom));
  if (p.yearTo) qs.set("year_to", String(p.yearTo));
  return `/v1/search/docs?${qs.toString()}`;
}

export const searchDocs = (p: DocSearchParams, signal?: AbortSignal) => request<DocSearchOut>(docSearchPath(p), { signal });

export function useDocSearch(p: DocSearchParams, enabled = true) {
  const path = docSearchPath(p);
  return useQuery({
    queryKey: ["search-docs", path],
    queryFn: ({ signal }) => searchDocs(p, signal),
    enabled: enabled && p.q.trim().length > 0,
    staleTime: 30_000,
  });
}
