/** TanStack Query 훅. 키는 ["run", id, …] 로 묶어 저장·복원 뒤 한꺼번에 무효화한다. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "./endpoints";
import type { EditRequest, FinalizeIn, ProposalRequest, RunState } from "./types";
import { isApiError } from "./client";

export const keys = {
  runs: ["runs"] as const,
  run: (id: string) => ["run", id] as const,
  draft: (id: string) => ["run", id, "draft"] as const,
  version: (id: string, v: number) => ["run", id, "version", v] as const,
  draftReview: (id: string) => ["run", id, "draft-review"] as const,
  finalReview: (id: string) => ["run", id, "final-review"] as const,
  versions: (id: string) => ["run", id, "versions"] as const,
  diff: (id: string, a: number, b: number) => ["run", id, "diff", a, b] as const,
  working: (id: string) => ["run", id, "working"] as const,
  renderCheck: (id: string) => ["run", id, "render-check"] as const,
  outline: (id: string) => ["run", id, "outline"] as const,
  sources: ["sources"] as const,
  search: (q: string) => ["search", q] as const,
};

const ACTIVE = new Set<RunState["status"]>(["queued", "running", "draft_reviewing", "final_reviewing"]);
export const isActive = (s: RunState["status"] | undefined) => !!s && ACTIVE.has(s);

/** 404 는 "없음" 으로 다루는 조회(설계도·임시 저장·검토 결과) */
function optional<T>(fn: () => Promise<T>): () => Promise<T | null> {
  return async () => {
    try {
      return await fn();
    } catch (e) {
      if (isApiError(e) && e.status === 404) return null;
      throw e;
    }
  };
}

export function useRuns() {
  return useQuery({ queryKey: keys.runs, queryFn: () => api.listRuns(50) });
}

export function useRun(id: string, opts: { poll?: boolean } = {}) {
  return useQuery({
    queryKey: keys.run(id),
    queryFn: () => api.getRun(id),
    refetchInterval: (q) => (opts.poll && isActive(q.state.data?.status) ? 2000 : false),
  });
}

export function useDraft(id: string, enabled = true) {
  return useQuery({ queryKey: keys.draft(id), queryFn: () => api.getDraft(id), enabled });
}

export function useVersion(id: string, version: number | null) {
  return useQuery({
    queryKey: keys.version(id, version ?? 0),
    queryFn: () => api.getVersion(id, version ?? 0),
    enabled: version !== null && version > 0,
  });
}

export function useDraftReview(id: string, enabled = true) {
  return useQuery({
    queryKey: keys.draftReview(id),
    queryFn: optional(() => api.getDraftReview(id)),
    enabled,
  });
}

export function useFinalReview(id: string, enabled = true) {
  return useQuery({
    queryKey: keys.finalReview(id),
    queryFn: optional(() => api.getFinalReview(id)),
    enabled,
  });
}

export function useOutline(id: string, enabled = true) {
  return useQuery({ queryKey: keys.outline(id), queryFn: optional(() => api.getOutline(id)), enabled });
}

export function useVersions(id: string) {
  return useQuery({ queryKey: keys.versions(id), queryFn: () => api.getVersions(id) });
}

export function useDiff(id: string, from: number | null, to: number | null) {
  return useQuery({
    queryKey: keys.diff(id, from ?? 0, to ?? 0),
    queryFn: () => api.getDiff(id, from ?? 0, to ?? 0),
    enabled: from !== null && to !== null && from !== to,
  });
}

export function useWorking(id: string, enabled = true) {
  return useQuery({ queryKey: keys.working(id), queryFn: optional(() => api.getWorking(id)), enabled });
}

export function useRenderCheck(id: string, enabled = true) {
  return useQuery({ queryKey: keys.renderCheck(id), queryFn: () => api.getRenderCheck(id), enabled });
}

export function useSources() {
  return useQuery({ queryKey: keys.sources, queryFn: api.getSources });
}

export function useSearch(q: string) {
  return useQuery({ queryKey: keys.search(q), queryFn: () => api.search(q, 10), enabled: q.trim().length > 0 });
}

export function useInvalidateRun(id: string) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: keys.run(id) });
}

export function useSaveVersion(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: EditRequest) => api.saveVersion(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.run(id) }),
  });
}

export function useRestore(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (version: number) => api.restoreVersion(id, version),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.run(id) }),
  });
}

export function useStartFinalReview(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.startFinalReview(id),
    onSuccess: (state) => {
      qc.setQueryData(keys.run(id), state);
      qc.invalidateQueries({ queryKey: keys.run(id) });
    },
  });
}

export function useFinalize(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: FinalizeIn) => api.finalizeRun(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.run(id) }),
  });
}

export function useReopen(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.reopenRun(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.run(id) }),
  });
}

export function useSubmitRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.submitRun,
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.runs }),
  });
}

export function usePrecheck() {
  return useMutation({ mutationFn: (req: ProposalRequest) => api.precheck(req) });
}
