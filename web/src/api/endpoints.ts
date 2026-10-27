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

// ── U1~U8 (feat/usability) ─────────────────────────
import type {
  BriefOut,
  ComparisonOut,
  EvidenceDecisionRequest,
  EvidenceOut,
  FeedbackIn,
  RewriteApplyIn,
  RewriteOut,
  SectionAnswersOut,
  SectionQuestionsOut,
  StructureMergeIn,
  StructureOut,
  SubmitCheckOut,
  UsageOut,
  VersionWithStatus,
} from "./types";

/** U2 간편 입력 — 자유 문장(+가제) → 4칸. 서버는 본문을 저장하지 않는다. 꺼짐·LLM 없음이면 503. */
export const structureIdea = (text: string, title = "") =>
  request<StructureOut>(`${V}/ideas/structure`, { method: "POST", body: { text, title } });
export const mergeStructure = (body: StructureMergeIn) =>
  request<StructureOut>(`${V}/ideas/structure/merge`, { method: "POST", body });
/** U4 차별성 비교표 (화면·API 표만) */
export const comparison = (req: ProposalRequest) =>
  request<ComparisonOut>(`${V}/precheck/comparison`, { method: "POST", body: req });
/** U5 선행연구 브리핑 */
export const brief = (req: ProposalRequest) =>
  request<BriefOut>(`${V}/precheck/brief`, { method: "POST", body: req });
/** U1 문장 근거 원문·적합성·판단 */
export const sentenceEvidence = (id: string, sid: string) =>
  request<EvidenceOut>(`${V}/runs/${enc(id)}/sentences/${enc(sid)}/evidence`);
export const decideEvidence = (id: string, body: EvidenceDecisionRequest) =>
  request<VersionWithStatus>(`${V}/runs/${enc(id)}/evidence-decisions`, { method: "POST", body });
/** U3 섹션 다시 쓰기·반영·보완 질문·답 */
export const rewriteSection = (id: string, key: string) =>
  request<RewriteOut>(`${V}/runs/${enc(id)}/sections/${enc(key)}/rewrite`, { method: "POST" });
export const applyRewrite = (id: string, key: string, body: RewriteApplyIn) =>
  request<VersionWithStatus>(`${V}/runs/${enc(id)}/sections/${enc(key)}/rewrite/apply`, { method: "POST", body });
export const sectionQuestions = (id: string, key: string) =>
  request<SectionQuestionsOut>(`${V}/runs/${enc(id)}/sections/${enc(key)}/questions`);
export const saveSectionAnswers = (id: string, key: string, answers: Record<string, string>) =>
  request<SectionAnswersOut>(`${V}/runs/${enc(id)}/sections/${enc(key)}/answers`, { method: "POST", body: { answers } });
/** U7 제출 전 점검 · U8 측정·만족도 */
export const getSubmitCheck = (id: string) => request<SubmitCheckOut>(`${V}/runs/${enc(id)}/submit-check`);
export const getUsage = (id: string) => request<UsageOut>(`${V}/runs/${enc(id)}/usage`);
export const sendFeedback = (id: string, body: FeedbackIn) =>
  request<UsageOut>(`${V}/runs/${enc(id)}/feedback`, { method: "POST", body });
