// 문제 정의 카드 (ADR 0065, docs/contracts/problem-card.md) — 0단계 계약. 레인은 고치지 않는다.
// 서버 모델 src/rra/domain/models/problem_card.py 와 같은 모양. 글은 외부 LLM 출력 또는 제안자 수정(비신뢰).

export type CardOrigin = "ai" | "user";
/** 근거 있음 = 제안문에 있는 내용, 추정 = AI 가 채운 내용(보완 질문으로 확인) */
export type CardBasis = "근거 있음" | "추정";
export type LadderLevel = "구체" | "일반화" | "추상화";
export type ProblemNature = "단순" | "난해" | "복잡";
export type ProjectMode = "도입형" | "실증형" | "연구형";
export type CardSignal =
  | "broad_scope"
  | "unclear_cause"
  | "safety_failure"
  | "policy_service"
  | "few_analogies";
export type CodeVerified = "table" | "corpus" | "kipris" | "unverified";
export type CardField =
  | "function_ko"
  | "function_en"
  | "ladder"
  | "terms"
  | "cause"
  | "contradiction"
  | "ipc"
  | "science_class"
  | "facets"
  | "nature";
export type CardRerun =
  | "derive"
  | "principles"
  | "codes"
  | "checks"
  | "analogy"
  | "clarify"
  | "plans_stale";

export interface CardText {
  /** 비어 있을 수 있다(근거가 없어 비워 둠) */
  value: string;
  origin: CardOrigin;
  basis: CardBasis;
  /** 사용자가 고치기 전 AI 값 */
  ai_value: string;
  /** 분석끼리 어긋남 → '확인 필요' */
  needs_check: boolean;
}

export interface ClassCode {
  code: string;
  /** 코드표·메타데이터의 이름. 없으면 빈 값 */
  label: string;
  origin: CardOrigin;
  /** unverified 면 '확인 못 함' — 검색에 쓰이지 않는다 */
  verified: CodeVerified;
  count: number | null;
}

export interface ProblemCard {
  version: number;
  facets: {
    phenomenon: CardText;
    target: CardText;
    place: CardText;
    cause: CardText;
    harm: CardText;
    desired: CardText;
  };
  function_ko: CardText;
  function_en: CardText;
  /** 구체 → 일반화 → 추상화 */
  ladder: { level: LadderLevel; text: string }[];
  ladder_origin: CardOrigin;
  terms: {
    objects_ko: string[];
    actions_ko: string[];
    objects_en: string[];
    actions_en: string[];
    origin: CardOrigin;
  };
  contradiction: {
    improve: string;
    worsen: string;
    principles: { number: number; name: string }[];
    origin: CardOrigin;
    basis: CardBasis;
    ai_improve: string;
    ai_worsen: string;
  };
  /** 근본 원인(2단계까지). 화면 '원인' 줄은 첫 칸 */
  causes: CardText[];
  ipc: ClassCode[];
  science_class: ClassCode[];
  nature: { kind: ProblemNature | null; mode: ProjectMode | null; origin: CardOrigin };
  signals: CardSignal[];
  methods: string[];
  checks: string[];
}

/** 화면 '핵심 문제' 4줄 — 서버가 만든 표시 문장 */
export interface CardLines {
  function: string;
  cause: string;
  contradiction: string;
  codes: string;
}

/** POST /v1/ideas/diagnose 요청 */
export interface DiagnoseIn {
  title_hint?: string;
  current_state: string;
  root_cause: string;
  limitation: string;
  goal: string;
  /** 화면이 갖고 있던 카드 — origin=user 항목은 서버가 그대로 둔다 */
  previous?: ProblemCard | null;
  /** true 면 고정·캐시를 건너뛰고 새로 진단한다 — [다시 정리] */
  refresh?: boolean;
}

/** POST /v1/ideas/diagnose 응답. status 가 off·failed 면 card 는 null — 카드 없이 진행한다 */
export interface DiagnoseOut {
  status: "ok" | "off" | "failed";
  card: ProblemCard | null;
  lines: CardLines | null;
  signal_labels: { signal: CardSignal; label: string }[];
  reason: string | null;
  reason_label: string | null;
  provider: string | null;
  model: string | null;
  fallback_local: boolean;
  seconds: number;
  /** 재사용한 카드인가 — pinned: 이 사용자가 확인해 고정한 카드, cached: 같은 제안문으로 전에 만든 카드, 없음·null: 새로 만듦 */
  reused?: "pinned" | "cached" | null;
}

/** POST /v1/ideas/diagnose/edit 요청 */
export interface CardEditIn {
  request: Omit<DiagnoseIn, "previous">;
  before: ProblemCard;
  after: ProblemCard;
  fields: CardField[];
}

/** POST /v1/ideas/diagnose/edit 응답. plans_stale 이면 ② 에 [과제안 다시 만들기] 를 보인다(자동 실행 없음) */
export interface CardEditOut {
  card: ProblemCard;
  lines: CardLines;
  reruns: CardRerun[];
  plans_stale: boolean;
  recorded: boolean;
}
