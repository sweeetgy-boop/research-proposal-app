/** 작성·편집 AI (레인 B, 2026-10-28) — 응답 모양은 entrypoints/views_editai.py·views.rewrite_payload 를 따라 손으로 적는다. */
import type { ProposalRequest, RewriteOut, RunIn, SectionQuestionsOut } from "./types";

export type PolicyDirection = "government" | "company" | "audit" | "regional";
export type PolicyChoiceMode = "card" | "merged" | "edited" | "manual" | "none";

/** 작성안이 인용한 원문 구간 — 문서명·연도·쪽·원문 인용·링크 (비신뢰) */
export interface PolicySource {
  chunk_id: string;
  doc_id: string;
  source: string;
  source_label: string;
  title: string;
  year: number | null;
  page: string | null;
  quote: string;
  url: string | null;
  trust?: "untrusted";
}

export interface PolicySentence {
  text: string;
  evidence: string[];
}

export interface PolicyCard {
  id: string;
  direction: PolicyDirection;
  direction_label: string;
  sentences: PolicySentence[];
  sources: PolicySource[];
}

/** 제안자가 정한 정책 근거 — RunIn.policy_choice · POST /v1/runs/{id}/policy-choice */
export interface PolicyChoice {
  mode: PolicyChoiceMode;
  card_ids?: string[];
  sentences: PolicySentence[];
  sources: PolicySource[];
}

/** 모델 호출 기록 (본문 없음) */
export interface AiTransfer {
  model?: string | null;
  fallback?: boolean;
  reason?: string | null;
  reason_label?: string | null;
  calls?: number;
  remote_calls?: number;
}

/** POST /v1/ideas/policy-cards · /v1/runs/{id}/policy-cards */
export interface PolicyCardsOut {
  notice?: string;
  cards: PolicyCard[];
  count: number;
  /** ok | empty(해당 없음) | filtered(규칙에 걸러짐) | failed(호출 실패) */
  status: "ok" | "empty" | "filtered" | "failed";
  status_label: string;
  reason: string | null;
  reason_label: string | null;
  passages: number;
  dropped: number;
  excluded_docs: string[];
  transfer: AiTransfer;
}

/** POST …/policy-cards/polish */
export interface PolicyPolishOut {
  notice?: string;
  choice: PolicyChoice | null;
  reason: string | null;
  reason_label: string | null;
  dropped: number;
  transfer: AiTransfer;
}

export type ClarifyTopic = "policy" | "budget_period" | "target" | "metric" | "other";

export interface ClarifyQuestionV2 {
  id: string;
  question: string;
  topic: ClarifyTopic;
  topic_label: string;
  hint?: string | null;
}

/** POST /v1/precheck/clarify (2026-10-28) — status 로 "질문 없음" 사유를 가른다 */
export interface ClarifyOutV2 {
  questions: ClarifyQuestionV2[];
  skip_allowed: boolean;
  /** ok | enough(입력 충분) | failed(생성 실패 — 다시 시도) | off(꺼짐) */
  status: "ok" | "enough" | "failed" | "off";
  status_label: string;
  reason: string | null;
  reason_label: string | null;
  /** argon | local | rule(앱 점검) | none */
  source: "argon" | "local" | "rule" | "none";
  policy_needed: boolean;
  transfer?: AiTransfer;
}

/** POST /v1/runs/{id}/sections/{key}/rewrite — 새 필드 */
export interface RewriteOutV2 extends RewriteOut {
  new_count?: number;
  reason?: string | null;
  reason_label?: string | null;
  /** rewrite | new (빈 섹션 새로 쓰기) */
  mode?: "rewrite" | "new";
  writer?: { provider: string | null; model: string | null; local_fallback: boolean; label: string } | null;
}

/** GET /v1/runs/{id}/sections/{key}/questions — 새 필드 */
export interface SectionQuestionsOutV2 extends SectionQuestionsOut {
  source?: "argon" | "local" | "checklist" | "none";
  source_label?: string;
  reason?: string | null;
  reason_label?: string | null;
  cached?: boolean;
  transfer?: AiTransfer;
}

export interface ChangeItem {
  type: string;
  label: string;
  count: number;
}

/** GET /v1/runs/{id}/changes — 마지막 검토 이후 바뀐 것 */
export interface ChangesOut {
  run_id: string;
  base_version: number;
  current_version: number;
  total: number;
  items: ChangeItem[];
}

export type PolicyCardsIn = ProposalRequest & { exclude_doc_ids?: string[] };
export type RunInEditAI = RunIn & { policy_choice?: PolicyChoice | null };
