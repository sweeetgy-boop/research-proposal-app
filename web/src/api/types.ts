/** 응답 모양 — openapi.json 은 요청 본문만 담으므로 응답은 entrypoints/views.py 를 따라 손으로 적는다.
 *  요청 본문 타입은 생성된 schema.d.ts(components.schemas)에서 가져온다. */
import type { components } from "./schema";
import type { DocRefOut, LocalReviewView } from "./types-laneB";

/** main 의 ProposalRequest 에는 아직 `supplement`(보강 질문 답)가 없다(feat/draft-quality 에만). 서버는 모르는 칸을 무시한다. */
export type ProposalRequest = components["schemas"]["ProposalRequest"] & { supplement?: string };
export type RunIn = components["schemas"]["RunIn"] & { supplement?: string };
export type EditRequest = components["schemas"]["EditRequest"];
export type SentenceEdit = components["schemas"]["SentenceEdit"];
export type SectionEdit = components["schemas"]["SectionEdit"];
export type WorkingIn = components["schemas"]["WorkingIn"];
export type FinalizeIn = components["schemas"]["FinalizeIn"];
export type ConfirmIn = components["schemas"]["ConfirmIn"];
export type DifferentiationTransferIn = components["schemas"]["DifferentiationTransferIn"];
/** [G] 그림 카드 — POST /v1/runs/{id}/figures/{fid} · POST /v1/runs/{id}/figures */
export type FigureActionIn = components["schemas"]["FigureActionIn"];
export type FigureAddIn = components["schemas"]["FigureAddIn"];

export interface Problem {
  type: string;
  title: string;
  status: number;
  detail: string;
}

export type SessionKind = "admin" | "staff" | "guest";

export interface SessionOut {
  csrf: string;
  expires_in: number;
  /** 로그인 종류 — 사번·가명 ID 는 화면에 오지 않는다 */
  kind: SessionKind;
  label: string;
}

export type SessionIn =
  | { kind: "token"; token: string }
  | { kind: "staff"; staff_no: string }
  | { kind: "guest"; id: string; password: string };

/** GET /healthz — 배포된 버전(커밋·시각). 인증 없음, 화면 하단 표시용 */
export interface HealthOut {
  status: string;
  version?: { commit: string; short: string; deployed_at: string; prs?: string[]; source?: string };
}

export interface SessionInfo {
  kind: SessionKind;
  label: string;
  staff_enabled?: boolean;
  guest_enabled?: boolean;
}

export type RunStatus =
  | "queued"
  | "running"
  | "interrupted"
  | "failed"
  | "invalid"
  | "draft_reviewing"
  | "drafted"
  | "editing"
  | "final_reviewing"
  | "final_reviewed"
  | "finalized";

export interface StepState {
  name: string;
  status: "pending" | "done" | "error" | "skipped";
  error: string | null;
}

export interface FlowSummary {
  status: RunStatus;
  draft_review_skipped: string | null;
  /** 한국어 설명 (예: "1차 검토 생략(같은 모델 작성)") */
  draft_review_skipped_label?: string | null;
  final_reviews: number;
  final_reviewed_version: number | null;
  stale_edits: number;
  stale: boolean;
  has_working: boolean;
}

/** 빈 초안 금지(ADR 0027): 로컬 작성이 실패해 빈칸으로 둔 섹션 — "이 섹션 다시 생성" 으로 채운다 */
export interface FailedSection {
  key: string;
  reason: string; // fence | json | schema | choices_only | empty | dropped
  label: string;
}

/** 대체 작성(ADR 0027): 로컬 2회 실패 뒤 외부 LLM(Gemini)이 쓴 섹션 — 화면은 "대체 작성" 배지만 */
export interface FallbackSection {
  key: string;
  provider: string;
  model: string;
  reason: string;
}

// ── [3] Argon 우선 작성 — 섹션마다 누가 썼는지. 옛 응답에는 없다(전부 선택). ─────────
export type WriterProvider = "gemini" | "mlx";
/** Argon(Gemini) 작성이 실패해 로컬 모델로 넘어간 사유 */
export type WriterReason = "error" | "rate_limit" | "budget" | "invalid";

export interface SectionWriter {
  provider: WriterProvider | string;
  model: string;
  /** true 면 Argon 실패 뒤 로컬 모델이 썼다 */
  local_fallback: boolean;
  reason: WriterReason | string | null;
}

/** 로컬 모델 근거 대조 — Argon 이 쓴 문장의 근거를 로컬 모델이 다시 맞춰 본 결과 */
export interface LocalCheck extends Omit<LocalReviewView, "enabled" | "mismatches" | "skipped_sections"> {
  enabled: boolean;
  mismatches: number;
  skipped_sections: string[];
}

// ── [4] 실시간 검색 — ② 유사과제 확인 때 외부 자료원을 바로 조회한 요약. 옛 응답에는 없다. ───
export type LiveSearchStatus = "done" | "partial" | "pending" | "off";
export type LiveSourceName = "scienceon" | "ntis" | "openalex";
export type LiveSourceStatus = "ok" | "timeout" | "ip_blocked" | "error" | "off";

export interface LiveSearchSource {
  source: LiveSourceName | string;
  status: LiveSourceStatus | string;
  count: number;
  seconds: number;
  /** 자료원 안내(NTIS IP 미등록 등) — 비신뢰 텍스트로 그린다 */
  notice: string | null;
}

export interface LiveSearch {
  status: LiveSearchStatus | string;
  keywords: { ko: string[]; en: string[] };
  sources: LiveSearchSource[];
}

export interface RunState {
  run_id: string;
  /** 항목 2 — 연구과제명(현재 버전 1-가, 없으면 가제). 모델 출력이라 텍스트로만 그린다 */
  title?: string | null;
  status: RunStatus;
  progress: [number, number];
  template: string;
  legacy: boolean;
  created_at: string;
  updated_at: string;
  steps: StepState[];
  draft_version: number;
  flow: FlowSummary;
  failed_sections?: FailedSection[];
  fallback_sections?: FallbackSection[];
  /** [3] run 전체 작성자 — gemini(Argon) 또는 local */
  writer?: "gemini" | "local" | string;
  local_sections?: string[];
  /** [4] 실시간 검색 요약 */
  live_search?: LiveSearch | null;
}

export interface RunList {
  runs: RunState[];
}

export interface OverlapAlert {
  doc_id: string;
  title: string;
  tier: string;
  similarity: number;
  blocking: boolean;
  basis: string | null;
  keywords: string[];
  status: string | null;
  own_detail: string | null;
  tier_label: string;
  status_label?: string | null;
  /** [4] 실시간 검색에서 찾은 과제 */
  live?: boolean;
}

export interface Transfer {
  public_doc_ids: string[];
  internal_doc_ids: string[];
  excluded_doc_ids: string[];
  calls: number;
}

export interface DifferentiationItem {
  doc_id: string;
  title: string;
  tier: string;
  status: string | null;
  overlap_summary: string;
  build_on: string;
  differentiation: string[];
  evidence: string[];
}

export interface Differentiation {
  skipped_reason: string | null;
  provider: string | null;
  model: string | null;
  fallback_local: boolean;
  transfer: Transfer;
  items: DifferentiationItem[];
  discarded: Record<string, unknown>[];
}

export interface Recommendation {
  index: number;
  title: string;
  summary: string;
  differentiation: string;
  reasons: string[];
  build_on: string;
  risks: string;
  compared_with: string[];
  evidence: string[];
  overlap_warning: string[];
}

export interface Recommendations {
  id: string;
  skipped_reason: string | null;
  no_recommendation_reason: string | null;
  provider: string | null;
  model: string | null;
  fallback_local: boolean;
  transfer: Transfer;
  recommendations: Recommendation[];
  discarded: Record<string, string>[];
}

/** ② 관련 연구(참고) — 논문·보고서·특허. 판정·차단에 쓰지 않는다 (ADR 0028). 제목은 비신뢰 텍스트. */
export interface RelatedResearch {
  doc_id: string;
  title: string;
  source: string;
  source_label: string;
  doc_type: string;
  year: number | null;
  similarity: number;
  url: string | null;
  /** [4] 실시간 검색에서 찾은 자료 */
  live?: boolean;
}

export interface PrecheckOut {
  notice: string;
  blocking: boolean;
  alerts: OverlapAlert[];
  related_research?: RelatedResearch[];
  differentiation?: Differentiation;
  recommendations?: Recommendations;
  /** [4] 실시간 검색 요약 */
  live_search?: LiveSearch | null;
}

/** POST /v1/precheck/ntis-outcomes — ② NTIS 과제(tier national_rnd) 주요 성과(참고용)·연관 과제 추천. 전부 비신뢰(NTIS API 출력). */
export interface NtisOutcome {
  kind: string; // paper | patent
  title: string;
  year: string | null;
  venue: string | null;
  result_id: string | null;
  registration_no: string | null;
}

export interface NtisProjectInsight {
  project_no: string;
  doc_id: string;
  title: string;
  tier: string;
  tier_label: string;
  similarity: number;
  blocking: boolean;
  cached: boolean;
  error: string | null;
  outcomes: NtisOutcome[];
}

export interface NtisRecommended {
  project_no: string;
  title: string;
  url: string;
  score: number | null;
  rank: number | null;
  source_project_no: string;
}

export interface NtisOutcomesOut {
  notice: string;
  projects: NtisProjectInsight[];
  ntis_recommended: NtisRecommended[];
}

export interface RecommendationPreview {
  notice: string;
  index: number;
  changed: string[];
  before: Record<string, string>;
  after: Record<string, string>;
  request: ProposalRequest;
}

export interface ClarifyQuestion {
  id?: string;
  field?: string;
  question: string;
  hint?: string;
}

export interface ClarifyOut {
  questions: (ClarifyQuestion | string)[];
  skip_allowed: boolean;
}

export type SentenceOrigin = string; // llm | argon | argon_added | proposer_edit | proposer_input | app …
export type SentenceSource = "retrieved" | "proposer_input" | "app";

export interface DraftSentence {
  sentence_id?: string;
  text: string;
  evidence: string[];
  source: SentenceSource;
  origin: SentenceOrigin;
}

export interface ChoiceOption {
  id: string;
  label: string;
}

export interface Choices {
  proposed: ChoiceOption[];
  confirmed: ChoiceOption[] | null;
  options: ChoiceOption[];
}

export interface DraftSection {
  key: string;
  sentences: DraftSentence[];
  choices: Choices | null;
}

export interface Citation {
  id: string;
  doc_id: string;
  title: string | null;
  /** [4] 실시간 검색에서 가져온 근거 */
  live?: boolean;
  /** ADR 0040 — 화면은 doc_id 대신 제목·자료원 이름(한국어)·원문 링크(공개 문서만) */
  source?: string;
  source_label?: string;
  url?: string | null;
}

export interface Problem_ {
  section: string;
  code: string;
  /** 한국어 설명 — 화면은 code 대신 이것 */
  label?: string;
  severity: string;
  severity_label?: string;
  message: string;
  sentence: number | null;
}

export interface ReviewSummary {
  rounds: number;
  skipped: boolean;
  error: string | null;
  model: string | null;
  latest_round: number | null;
  latest_kind: string | null;
  latest_status: string | null;
  open_comments: number;
  finalized_at: string | null;
}

export interface DraftStep extends StepState {
  sentences: number;
  dropped: number;
  parse: string | null;
  raw_chars: number | null;
  retries: number;
}

// ── [G] 제안서 그림 (figure cards) ─────────────────────────
export type FigureKind = "concept" | "process" | "schedule" | "stat_chart" | "comparison" | "roadmap";
export type FigureRenderer = "nano_banana" | "baseline";

/** 그림 안 글자 한 칸 — [글자 고치기] 는 바뀐 path 만 보낸다 */
export interface FigureText {
  path: string;
  label: string;
  value: string;
}

/** 그림 한 장. caption·alt·texts·error 는 LLM 출력(비신뢰). image_url 은 같은 출처(쿠키 인증) PNG/JPEG. */
export interface Figure {
  id: string;
  kind: FigureKind;
  label: string;
  section: string;
  caption: string;
  alt: string;
  renderer: FigureRenderer;
  renderer_label: string;
  model: string | null;
  calls: number;
  included: boolean;
  confirmed: boolean;
  source_caption: string;
  error: string | null;
  image_url: string;
  baseline_url: string;
  texts: FigureText[];
  edit_requests: number;
  /** 명세를 쓴 모델 (Argon 먼저, 실패면 로컬). 옛 run 은 없음 */
  spec_model?: string | null;
  /** 마지막 [말로 고치기]·[글자 고치기] 의 "바뀐 내용". summary·style 은 LLM 출력(비신뢰) */
  last_change?: FigureLastChange | null;
  updated_at: string | null;
  notice: string;
}

/** content = 명세(글자·단계·순서)가 바뀌어 밑그림부터 새로 그림, style = 명세 그대로 모양만 */
export interface FigureLastChange {
  kind: "content" | "style";
  summary: string[];
  style: string;
  model: string | null;
  at: string | null;
}

/** GET /v1/runs/{id}/figures */
export interface FiguresOut {
  run_id: string;
  version: number;
  figures: Figure[];
}

export type FigureChangeKind = "added" | "removed" | "redrawn" | "texts" | "included" | "excluded" | "confirmed" | "baseline";

export interface FigureChange {
  figure_id: string;
  kind: FigureKind | string;
  section: string;
  change: FigureChangeKind | string;
}

export interface DraftOut {
  notice: string;
  run_id: string;
  status: RunStatus;
  template: string;
  legacy: boolean;
  progress: [number, number];
  steps: DraftStep[];
  sections: DraftSection[];
  citations: Citation[];
  problems: Problem_[];
  version: number;
  versions: number[];
  review: ReviewSummary;
  flow: FlowSummary;
  failed_sections?: FailedSection[];
  fallback_sections?: FallbackSection[];
  /** [3] 섹션별 작성자 */
  writers?: Record<string, SectionWriter>;
  /** [3] Argon 실패 뒤 로컬 모델이 쓴 섹션 */
  local_sections?: string[];
  /** [3] 로컬 근거 대조 */
  local_check?: LocalCheck | null;
  /** [G] 그림 카드 — 옛 응답에는 없을 수 있다 */
  figures?: Figure[];
}

export interface Score {
  criterion: string;
  score: number;
  weak: boolean;
  reason: string;
  sentence_ids: string[];
}

export interface ReviewComment {
  id: string;
  section: string;
  sentence: number | null;
  sentence_id: string | null;
  kind?: "revision" | "addition" | string;
  after?: string | null;
  issue_type: string;
  comment: string;
  revised_text: string | null;
  evidence: string[];
  /** ADR 0040 — 근거 표시 정보 (제목·자료원 이름) */
  evidence_refs?: DocRefOut[];
  status: "open" | "resolved" | "discarded";
  usable: boolean;
  discard_reason: string | null;
}

export interface CandidateChoice {
  chosen?: string | number;
  rejected_text?: string | null;
  reason?: string;
  [k: string]: unknown;
}

export interface ReviewOut {
  notice: string;
  round: number;
  kind: "draft" | "final";
  final_round: number | null;
  draft_version: number;
  applied_ids: string[];
  applied_version: number | null;
  score_delta: Record<string, number>;
  candidate_choices?: Record<string, CandidateChoice>;
  checklist?: Record<string, unknown>;
  checklist_coverage?: number | null;
  status: "done" | "skipped" | "error";
  skipped_reason: string | null;
  created_at: string | null;
  excluded_sentences: string[];
  resolved_ids: string[];
  scores: Score[];
  transfer: {
    provider: string | null;
    model: string | null;
    public_doc_ids: string[];
    internal_doc_ids: string[];
    sentences_sent: number;
    sentences_excluded: number;
    calls: number;
  };
  comments: ReviewComment[];
}

export interface Annotation {
  id: string;
  section: string;
  sentence: number | null;
  sentence_id: string | null;
  kind: "opinion" | "discarded" | "section";
  text: string;
  reason: string | null;
  status: "open" | "done";
}

export interface VersionSentence {
  sentence_id: string;
  text: string;
  evidence: string[];
  origin: SentenceOrigin;
  source: SentenceSource;
}

export interface VersionSection {
  key: string;
  sentences: VersionSentence[];
  choices: string[];
}

export interface VersionMeta {
  version: number;
  origin: string;
  origin_label: string;
  created_at: string | null;
  based_on_review: number | null;
  reverted_from: number | null;
  note: string;
  changed_sections: string[];
  sentences?: number;
  alerts: number;
  open_annotations: number;
  /** [G] 그 버전의 그림 수 */
  figures?: number;
}

/** 버전 본문 — 목록 행(VersionMeta)과 달리 `figures` 는 그림 배열이다 */
export interface VersionOut extends Omit<VersionMeta, "figures"> {
  notice?: string;
  run_id?: string;
  status?: RunStatus;
  stale_edits?: number;
  annotations: Annotation[];
  sections: VersionSection[];
  /** [G] 그 버전의 그림 */
  figures?: Figure[];
}

export interface VersionsOut {
  run_id: string;
  versions: VersionMeta[];
}

export interface DiffRow {
  sentence_id: string;
  text: string;
  from?: number;
  to?: number;
}

export interface DiffSection {
  section: string;
  added: DiffRow[];
  removed: DiffRow[];
  moved: DiffRow[];
  choices_changed: boolean;
  sentences: [number, number];
}

export interface DiffOut {
  run_id: string;
  notice: string;
  from: number;
  to: number;
  sections: DiffSection[];
  /** [G] 그림 변경 */
  figures_changed?: FigureChange[];
}

export interface WorkingSection {
  section: string;
  texts?: string[];
  text?: string;
}

export interface WorkingOut {
  run_id: string;
  notice: string;
  working: {
    sections: WorkingSection[];
    note: string;
    base_version: number | null;
    saved_at: string;
  };
}

export interface RenderCheckOut {
  run_id: string;
  count: number;
  unsupported_numbers: number;
  unresolved: Problem_[];
  overflow: { slot: string; label: string; chars: number; limit: number; kind: string }[];
  notes: string[];
}

export interface ConfirmOut {
  run_id: string;
  confirmed: Record<string, string[]>;
}

export interface SearchChunk {
  chunk_id: string;
  doc_id: string;
  ordinal: number;
  basis: string | null;
  similarity: number | null;
  text: string;
  trust: "untrusted";
}

export interface SearchOut {
  notice: string;
  chunks: SearchChunk[];
}

export interface SourceStatus {
  source: string;
  label: string;
  count: number;
  last_ingested: string | null;
  /** 차단 안내 (IP 거부 등, 레인 I). 평소 null. */
  notice?: string | null;
}

export interface SourcesOut {
  sources: SourceStatus[];
}

export interface OutlineOut {
  run_id: string;
  notice: string;
  outline: Record<string, unknown> | unknown[];
}

// ── U1~U8 (feat/usability, 2026-10-27) ─────────────────────────
export type StructureIn = components["schemas"]["StructureIn"];
export type StructureMergeIn = components["schemas"]["StructureMergeIn"];
export type EvidenceDecisionRequest = components["schemas"]["EvidenceDecisionRequest"];
export type EvidenceDecisionIn = components["schemas"]["EvidenceDecision"];
export type RewriteApplyIn = components["schemas"]["RewriteApplyIn"];
export type SectionAnswersIn = components["schemas"]["SectionAnswersIn"];
export type FeedbackIn = components["schemas"]["FeedbackIn"];

export type StructureField = "current_state" | "root_cause" | "limitation" | "goal";

export interface StructureQuestion {
  field: StructureField;
  label: string;
  question: string;
  reason: "empty" | "short" | string;
}

/** POST /v1/ideas/structure · /merge */
export interface StructureOut {
  notice: string;
  fields: Record<StructureField, string>;
  labels: Record<string, string>;
  questions: StructureQuestion[];
  skip_allowed: boolean;
  complete: boolean;
  provider: string | null;
  model: string | null;
  parse_failed: boolean;
}

export type ComparisonAspect = "objective" | "method" | "scope" | "outcome" | "differentiation";

export interface ComparisonColumn {
  doc_id: string | null;
  title: string;
  tier: string | null;
  similarity: number | null;
  blocking: boolean;
  basis: string | null;
  title_only: boolean;
  cells: Record<ComparisonAspect | string, string>;
}

/** POST /v1/precheck/comparison */
export interface ComparisonOut {
  notice: string;
  blocking: boolean;
  alerts: OverlapAlert[];
  comparison: {
    aspects: { key: ComparisonAspect | string; label: string }[];
    proposal: ComparisonColumn;
    projects: ComparisonColumn[];
  };
}

export interface BriefItem {
  doc_id: string;
  chunk_id: string;
  title: string;
  source: string;
  doc_type: string;
  year: number | null;
  basis: string | null;
  summary: string;
  summary_missing: boolean;
}

export interface GapCandidate {
  text: string;
  evidence: string[];
}

/** POST /v1/precheck/brief */
export interface BriefOut {
  notice: string;
  skipped_reason: string | null;
  provider: string | null;
  model: string | null;
  fallback_local: boolean;
  transfer: Transfer;
  items: BriefItem[];
  years: Record<string, number>;
  keywords: string[];
  gap_label: string;
  gaps: GapCandidate[];
  discarded: Record<string, string>[];
}

export type EvidenceSupport = "지지" | "부분" | "불일치" | string;
export type DecisionAction = "approve" | "replace" | "exclude";

export interface EvidenceItem {
  evidence_id: string;
  doc_id: string;
  chunk_id: string;
  text: string;
  title: string | null;
  source: string;
  source_label: string;
  orgs: string[];
  year: number | null;
  ingested_at: string | null;
  basis: string | null;
  basis_label: string;
  needs_check: boolean;
  needs_check_label: string | null;
  support: EvidenceSupport | null;
  decision: DecisionAction | null;
  in_snapshot: boolean;
  trust: "untrusted";
  /** [4] 실시간 검색에서 가져온 근거 */
  live?: boolean;
  /** 원문 링크 */
  url?: string | null;
}

/** GET /v1/runs/{id}/sentences/{sid}/evidence */
export interface EvidenceOut {
  run_id: string;
  sentence_id: string;
  notice: string;
  evidence: EvidenceItem[];
}

export interface EvidenceDecisionRecord {
  sentence_id: string;
  evidence_id: string;
  action: DecisionAction;
}

/** POST /v1/runs/{id}/evidence-decisions · …/rewrite/apply → 상태 + 버전 */
export interface VersionWithStatus extends VersionOut {
  run_id: string;
  status: RunStatus;
  evidence_decisions?: EvidenceDecisionRecord[];
}

export interface RewriteSentence {
  text: string;
  evidence: string[];
  origin: SentenceOrigin;
  preserved?: boolean;
}

export interface RewriteRow {
  index: number;
  current: RewriteSentence | null;
  candidate: RewriteSentence | null;
}

/** POST /v1/runs/{id}/sections/{key}/rewrite */
export interface RewriteOut {
  run_id: string;
  notice: string;
  section: string;
  created_at: string | null;
  dropped: number;
  rows: RewriteRow[];
  candidate: { index: number; text: string; evidence: string[]; origin: SentenceOrigin; source: SentenceSource }[];
  choices: string[];
}

/** GET /v1/runs/{id}/sections/{key}/questions */
export interface SectionQuestionsOut {
  run_id: string;
  section: string;
  questions: { element: string; question: string }[];
  coverage: number | null;
  answers: Record<string, string>;
}

export interface SectionAnswersOut {
  run_id: string;
  section: string;
  answers: Record<string, string>;
}

export type CheckTarget = `section:${string}` | `sentence:${string}` | `route:${string}` | null;

export interface SubmitCheckItem {
  key: string;
  label: string;
  ok: boolean;
  detail: string;
  count: number;
  target: CheckTarget;
  target_label: string | null;
  /** 항목별 추가 정보 (strategy_source: source·options, evidence_approval: rate …) */
  [extra: string]: unknown;
}

/** GET /v1/runs/{id}/submit-check */
export interface SubmitCheckOut {
  run_id: string;
  ok: boolean;
  failing: number;
  items: SubmitCheckItem[];
}

export interface UsageRecord {
  run_id: string;
  step_seconds: Record<string, number>;
  /** 화면용 줄 목록 (옛 응답에는 없다) */
  steps?: import("./types-format").UsageStepRow[];
  total_seconds: number;
  total_label?: string;
  checklist_coverage: number | null;
  evidence: { approve: number; replace: number; exclude: number; total: number; ratios: Record<string, number> };
  rewrites: number;
  hwpx_success: boolean | null;
  satisfaction: { score: number; comment: string; recorded_at: string | null } | null;
  updated_at: string | null;
}

/** GET /v1/runs/{id}/usage · POST …/feedback */
export interface UsageOut {
  run_id: string;
  usage: UsageRecord | null;
}
export * from "./types-figures"; // [G] 그림 v2 (레인 C)
export * from "./types-editai";
export * from "./types-precheck"; // ② 유사과제 흐름 (레인 A)
export * from "./types-format"; // 레인 D
export * from "./types-laneB"; // 레인 B — L2 로컬 2차 검토·문서 표시 (ADR 0040)
