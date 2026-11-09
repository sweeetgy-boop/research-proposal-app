/** TanStack Query 훅. 키는 ["run", id, …] 로 묶어 저장·복원 뒤 한꺼번에 무효화한다. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "./endpoints";
import type { EditRequest, EvidenceDecisionRequest, FeedbackIn, FigureActionIn, FigureAddIn, FinalizeIn, ProposalRequest, RewriteApplyIn, RunState } from "./types";
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
  figures: (id: string) => ["run", id, "figures"] as const,
  sources: ["sources"] as const,
  health: ["health"] as const,
  search: (q: string) => ["search", q] as const,
};

/** 배포 버전(화면 하단). 실패해도 화면은 그대로 — 표시만 생략 */
export function useDeployVersion() {
  return useQuery({ queryKey: keys.health, queryFn: api.getHealth, staleTime: 5 * 60_000, retry: false });
}

/** Argon 연결 상태(화면 위 알림 띠, ADR 0055) — 하단 버전과 같은 /healthz 캐시. 로그인 뒤에만 60초마다·창으로
 *  돌아올 때 다시 읽는다(추가 모델 호출 없음, 서버는 마지막 호출 결과만 돌려준다). */
export const ARGON_POLL_MS = 60_000;
export function useArgonStatus(enabled: boolean) {
  return useQuery({
    queryKey: keys.health,
    queryFn: api.getHealth,
    enabled,
    staleTime: 30_000,
    refetchInterval: enabled ? ARGON_POLL_MS : false,
    refetchOnWindowFocus: true,
    retry: false,
    select: (h) => h.llm ?? null,
  });
}

/** 운영 상태(계약 docs/contracts/healthz-status.md) — 같은 /healthz 캐시에서 `tunnel`·`llm.local` 만. 관리자 띠용 */
export function useOpsStatus(enabled: boolean) {
  return useQuery({
    queryKey: keys.health,
    queryFn: api.getHealth,
    enabled,
    staleTime: 30_000,
    refetchInterval: enabled ? ARGON_POLL_MS : false,
    refetchOnWindowFocus: true,
    retry: false,
    select: (h) => ({ tunnel: h.tunnel ?? "unknown", local: h.llm?.local ?? "unknown" }),
  });
}

const ACTIVE = new Set<RunState["status"]>(["queued", "running", "draft_reviewing", "final_reviewing"]);
export const isActive = (s: RunState["status"] | undefined) => !!s && ACTIVE.has(s);
/** 그림 백그라운드 작업 중 (ADR 0045, features/figures/figureJob.ts 와 같은 규칙) */
const drawingFigures = (r: RunState | undefined) => {
  const s = (r as { figures_status?: string | null } | undefined)?.figures_status;
  return s === "pending" || s === "drawing";
};

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
    // 생성·검토 중이거나 그림을 백그라운드로 그리는 중(ADR 0045)이면 2초마다
    refetchInterval: (q) => (opts.poll && (isActive(q.state.data?.status) || drawingFigures(q.state.data)) ? 2000 : false),
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

// ── U1~U8 ─────────────────────────────────────
export const usabilityKeys = {
  evidence: (id: string, sid: string) => ["run", id, "evidence", sid] as const,
  questions: (id: string, key: string) => ["run", id, "questions", key] as const,
  submitCheck: (id: string) => ["run", id, "submit-check"] as const,
  usage: (id: string) => ["run", id, "usage"] as const,
};

/** 503(기능 꺼짐·LLM 없음)은 "없음" 으로 다루는 조회 */
function unavailable<T>(fn: () => Promise<T>): () => Promise<T | null> {
  return async () => {
    try {
      return await fn();
    } catch (e) {
      if (isApiError(e) && (e.status === 503 || e.status === 404)) return null;
      throw e;
    }
  };
}

export function useSentenceEvidence(id: string, sid: string | null) {
  return useQuery({
    queryKey: usabilityKeys.evidence(id, sid ?? ""),
    queryFn: () => api.sentenceEvidence(id, sid ?? ""),
    enabled: sid !== null,
  });
}

export function useSectionQuestions(id: string, key: string | null) {
  return useQuery({
    queryKey: usabilityKeys.questions(id, key ?? ""),
    queryFn: unavailable(() => api.sectionQuestions(id, key ?? "")),
    enabled: key !== null,
  });
}

export function useSubmitCheck(id: string, enabled = true) {
  return useQuery({ queryKey: usabilityKeys.submitCheck(id), queryFn: unavailable(() => api.getSubmitCheck(id)), enabled });
}

export function useUsage(id: string, enabled = true) {
  return useQuery({ queryKey: usabilityKeys.usage(id), queryFn: unavailable(() => api.getUsage(id)), enabled });
}

export function useDecideEvidence(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: EvidenceDecisionRequest) => api.decideEvidence(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.run(id) }),
  });
}

export function useApplyRewrite(id: string, key: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RewriteApplyIn) => api.applyRewrite(id, key, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.run(id) }),
  });
}

export function useFeedback(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: FeedbackIn) => api.sendFeedback(id, body),
    onSuccess: (out) => qc.setQueryData(usabilityKeys.usage(id), out),
  });
}

// ── [G] 그림 카드 ─────────────────────────────
export function useFigures(id: string, enabled = true) {
  return useQuery({ queryKey: keys.figures(id), queryFn: () => api.getFigures(id), enabled });
}

/** 그림 동작 → 새 버전. 성공하면 run 아래 전부 무효화 (초안·버전·그림). */
export function useFigureAction(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ fid, body }: { fid: string; body: FigureActionIn }) => api.figureAction(id, fid, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.run(id) }),
  });
}

export function useAddFigure(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: FigureAddIn) => api.addFigure(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.run(id) }),
  });
}
