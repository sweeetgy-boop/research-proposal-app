/** 경로별 호출 함수 — docs/openapi.json 28 경로 중 화면이 쓰는 것. */
import { rawRequest, request } from "./client";
import { clearSession, setSession } from "@/auth/session";
import type {
  ClarifyOut,
  ConfirmIn,
  ConfirmOut,
  DiffOut,
  DraftOut,
  EditRequest,
  FinalizeIn,
  OutlineOut,
  PrecheckOut,
  ProposalRequest,
  RecommendationPreview,
  RenderCheckOut,
  ReviewOut,
  RunIn,
  RunList,
  RunState,
  SearchOut,
  SessionOut,
  SourcesOut,
  VersionOut,
  VersionsOut,
  WorkingIn,
  WorkingOut,
} from "./types";

const V = "/v1";
const enc = encodeURIComponent;

// ── 세션 ─────────────────────────────────────
export async function login(token: string): Promise<SessionOut> {
  const out = await request<SessionOut>(`${V}/session`, {
    method: "POST",
    body: { token },
    keepSessionOn401: true,
  });
  setSession(out.csrf);
  return out;
}

export async function logout(): Promise<void> {
  try {
    await request<void>(`${V}/session`, { method: "DELETE" });
  } finally {
    clearSession();
  }
}

// ── 자료원·검색·사전 점검 ──────────────────────
export const getSources = () => request<SourcesOut>(`${V}/sources/status`);
export const search = (q: string, k = 10) =>
  request<SearchOut>(`${V}/search?q=${enc(q)}&k=${k}`);
export const precheck = (req: ProposalRequest) =>
  request<PrecheckOut>(`${V}/precheck`, { method: "POST", body: req });
export const clarify = (req: ProposalRequest) =>
  request<ClarifyOut>(`${V}/precheck/clarify`, { method: "POST", body: req });
export const recommend = (req: ProposalRequest) =>
  request<PrecheckOut>(`${V}/precheck/recommendations`, { method: "POST", body: req });
export const applyRecommendation = (id: string, index: number) =>
  request<RecommendationPreview>(`${V}/precheck/recommendations/${enc(id)}/apply`, {
    method: "POST",
    body: { index },
  });
export const differentiate = (req: ProposalRequest) =>
  request<PrecheckOut>(`${V}/precheck/differentiate`, { method: "POST", body: req });

// ── run ───────────────────────────────────────
export const submitRun = (body: RunIn) => request<RunState>(`${V}/runs`, { method: "POST", body });
export const listRuns = (limit = 50) => request<RunList>(`${V}/runs?limit=${limit}`);
export const getRun = (id: string) => request<RunState>(`${V}/runs/${enc(id)}`);
export const resumeRun = (id: string) =>
  request<RunState>(`${V}/runs/${enc(id)}/resume`, { method: "POST" });
export const getDraft = (id: string) => request<DraftOut>(`${V}/runs/${enc(id)}/draft`);
export const getVersion = (id: string, version: number) =>
  request<VersionOut>(`${V}/runs/${enc(id)}/draft?version=${version}`);
export const getDraftReview = (id: string) =>
  request<ReviewOut>(`${V}/runs/${enc(id)}/draft-review`);
export const getOutline = (id: string) => request<OutlineOut>(`${V}/runs/${enc(id)}/outline`);
export const getVersions = (id: string) => request<VersionsOut>(`${V}/runs/${enc(id)}/versions`);
export const saveVersion = (id: string, body: EditRequest) =>
  request<VersionOut>(`${V}/runs/${enc(id)}/versions`, { method: "POST", body });
export const getDiff = (id: string, from: number, to: number) =>
  request<DiffOut>(`${V}/runs/${enc(id)}/versions/diff?from=${from}&to=${to}`);
export const restoreVersion = (id: string, version: number) =>
  request<VersionOut>(`${V}/runs/${enc(id)}/versions/${version}/restore`, { method: "POST" });
export const getWorking = (id: string) => request<WorkingOut>(`${V}/runs/${enc(id)}/draft/working`);
export const putWorking = (id: string, body: WorkingIn) =>
  request<{ run_id: string; saved: boolean }>(`${V}/runs/${enc(id)}/draft/working`, {
    method: "PUT",
    body,
  });
export const deleteWorking = (id: string) =>
  request<void>(`${V}/runs/${enc(id)}/draft/working`, { method: "DELETE" });
export const startFinalReview = (id: string) =>
  request<RunState>(`${V}/runs/${enc(id)}/final-review`, { method: "POST" });
export const getFinalReview = (id: string, round?: number) =>
  request<ReviewOut>(
    `${V}/runs/${enc(id)}/final-review${round ? `?round=${round}` : ""}`,
  );
export const getRenderCheck = (id: string) =>
  request<RenderCheckOut>(`${V}/runs/${enc(id)}/render-check`);
export const confirmChoices = (id: string, body: ConfirmIn) =>
  request<ConfirmOut>(`${V}/runs/${enc(id)}/confirm`, { method: "POST", body });
export const reopenRun = (id: string) =>
  request<RunState>(`${V}/runs/${enc(id)}/reopen`, { method: "POST" });

export interface FinalizeResult {
  blob: Blob;
  filename: string;
  version: string | null;
  status: string | null;
  check: RenderCheckOut | null;
}

/** HWPX 파일 응답. 제안자 정보는 이 요청 본문에만 실리고 어디에도 저장하지 않는다. */
export async function finalizeRun(id: string, body: FinalizeIn): Promise<FinalizeResult> {
  const res = await rawRequest(`${V}/runs/${enc(id)}/finalize`, { method: "POST", body });
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") ?? "";
  const m = /filename="?([^";]+)"?/.exec(cd);
  let check: RenderCheckOut | null = null;
  const raw = res.headers.get("x-rra-check");
  if (raw) {
    try {
      check = JSON.parse(raw) as RenderCheckOut;
    } catch {
      check = null;
    }
  }
  return {
    blob,
    filename: m?.[1] ?? `proposal-${id}.hwpx`,
    version: res.headers.get("x-rra-version"),
    status: res.headers.get("x-rra-status"),
    check,
  };
}
