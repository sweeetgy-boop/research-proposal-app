/** 응답 모양 — openapi.json 은 요청 본문만 담으므로 응답은 entrypoints/views.py 를 따라 손으로 적는다.
 *  요청 본문 타입은 생성된 schema.d.ts(components.schemas)에서 가져온다. */
import type { components } from "./schema";

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

export interface Problem {
  type: string;
  title: string;
  status: number;
  detail: string;
}

export interface SessionOut {
  csrf: string;
  expires_in: number;
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
  final_reviews: number;
  final_reviewed_version: number | null;
  stale_edits: number;
  stale: boolean;
  has_working: boolean;
}

export interface RunState {
  run_id: string;
  status: RunStatus;
  progress: [number, number];
  template: string;
  legacy: boolean;
  created_at: string;
  updated_at: string;
  steps: StepState[];
  draft_version: number;
  flow: FlowSummary;
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

export interface PrecheckOut {
  notice: string;
  blocking: boolean;
  alerts: OverlapAlert[];
  differentiation?: Differentiation;
  recommendations?: Recommendations;
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
}

export interface Problem_ {
  section: string;
  code: string;
  severity: string;
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
}

export interface VersionOut extends VersionMeta {
  notice?: string;
  run_id?: string;
  status?: RunStatus;
  stale_edits?: number;
  annotations: Annotation[];
  sections: VersionSection[];
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
  total_seconds: number;
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
