/** ①~③ 사이에 들고 다니는 제안자 입력. 새로고침에 견디도록 sessionStorage 에 둔다
 *  (아이디어 본문뿐 — 개인정보·토큰 없음). */
import { useSyncExternalStore } from "react";
import type { BriefOut, ChoiceSource, ComparisonOut, DifferentiationTransferIn, PlanField, PrecheckOut, PrecheckRequest, SimilarChoice, SimilarChoiceValue } from "@/api/types";
import type { CardLines, DiagnoseOut, ProblemCard } from "@/api/types-problem-card";
import { inferSources } from "@/features/precheck/model";
import { emptyRequest } from "@/lib/validation";

/** 들고 다니는 입력 — [다음] 때 쓸 수 있는 문제 정의 카드가 있으면 problem_card 로 함께 간다 (ADR 0065).
 *  과제안(/v1/precheck/recommendations)·보강 질문·초안 생성 요청에 실리고, ② 판정·비교표 요청에는 싣지 않는다(withoutCard). */
export type IdeaRequest = PrecheckRequest;

export interface IdeaState {
  request: IdeaRequest;
  precheck: PrecheckOut | null;
  acknowledged: boolean;
  recommendationId: string | null;
  recommendationIndex: number | null;
  differentiationTransfer: DifferentiationTransferIn | null;
  clarifyAnswers: { question: string; answer: string }[];
  /** ① 입력 방식 — 간편(자유 문장 → 4칸) / 상세(4칸 직접). 기본 간편. */
  inputMode: "quick" | "detail";
  /** 간편 입력 본문·가제 (새로고침에 견디도록; 개인정보 없음) */
  quickText: string;
  quickTitle: string;
  /** ② 차별성 비교표 · 브리핑 결과 (입력이 바뀌면 다시 받는다) */
  comparison: ComparisonOut | null;
  brief: BriefOut | null;
  /** 브리핑에서 고른 우선 근거 id (doc_id·chunk_id) → POST /v1/runs priority_evidence */
  priorityEvidence: string[];
  /** ② 행별 선택 [유사함]/[관련 없음] — doc_id → 선택 (레인 A). request.similar_choices 로 서버에 간다 */
  similarChoices: Record<string, SimilarChoiceValue>;
  /** 행별 선택의 출처 — doc_id → user(제안자가 직접 바꿈) / ai_prefill(미리 고른 AI 기본 선택 그대로). 선택 기록용 (ADR 0056) */
  choiceSources: Record<string, ChoiceSource>;
  /** 과제안(추천)을 만든 시점의 [유사함] 선택 서명 — 바뀌면 [과제안 다시 만들기] 를 권한다 */
  planSig: string | null;
  /** ② 에 들어올 때의 원래 아이디어 과제안 칸 (원래 아이디어 유지·비교용) */
  originalPlan: Record<PlanField, string> | null;
  /** 지금 입력의 과제안 출처 */
  planSource: "original" | "card" | "edited";
  /** ② [선택 적용] 한 선택 — 비교표·활용 제안·과제안 근거는 이 선택으로 만든다 (레인 A, ADR 0039) */
  appliedChoices: Record<string, SimilarChoiceValue> | null;
  /** [선택 적용] 한 선택의 출처 (ADR 0056) */
  appliedChoiceSources: Record<string, ChoiceSource> | null;
  /** ① 정책 근거 추천 팝업에서 [나중에 넣기] — [다음] 때 다시 묻지 않는다 (ADR 0052) */
  policyDeferred: boolean;
  /** ② 관련 연구에서 [차별화에 참고] 로 고른 doc_id (최대 5, 고른 순서). request.reference_ids 로 서버에 간다 — 판정·차단에는 쓰지 않는다 (ADR 0053) */
  referenceIds: string[];
  /** [선택 적용] 한 참고 논문 — 비교표·활용 제안은 이 목록으로 만든다 */
  appliedReferenceIds: string[] | null;
  /** 과제안(추천)을 만든 시점의 참고 논문 서명 — 바뀌면 [과제안 다시 만들기] 를 권한다 */
  planRefSig: string | null;
  /** ① '핵심 문제' 카드 (ADR 0065) — 없거나 null 이면 카드 없이 종전대로. 옛 화면 상태에는 이 칸들이 없다(선택 칸) */
  problemCard?: ProblemCard | null;
  /** 카드 4줄의 표시 문장(서버가 만든 것) */
  cardLines?: CardLines | null;
  /** 켜진 신호의 한국어 라벨 — 1차는 받아 두기만 하고 화면에 그리지 않는다 */
  cardSignals?: DiagnoseOut["signal_labels"];
  /** 진단을 마친(성공·꺼짐·실패 모두) 네 칸의 서명 — 지금 네 칸과 다르면 다시 진단한다 */
  cardSig?: string | null;
  /** 카드를 고쳐 이미 받은 과제안이 옛 문제 정의 기준이다 → ② 에 [과제안 다시 만들기] 한 줄(자동 실행 없음) */
  plansStale?: boolean;
}

/** 진단에 쓰는 네 칸의 서명 — 한 칸이라도 비면 null(진단하지 않는다). 앞뒤 공백은 무시 */
export function fourSignature(r: Pick<PrecheckRequest, "current_state" | "root_cause" | "limitation" | "goal">): string | null {
  const four = [r.current_state, r.root_cause, r.limitation, r.goal].map((v) => (v ?? "").trim());
  return four.every(Boolean) ? JSON.stringify(four) : null;
}

/** 카드를 뗀 입력 — ② 판정·비교표·활용 제안처럼 카드를 쓰지 않는 요청과 그 캐시 키에 */
export function withoutCard<T extends { problem_card?: unknown }>(r: T): Omit<T, "problem_card"> {
  const { problem_card: _drop, ...rest } = r;
  void _drop;
  return rest;
}

const KEY = "rra-idea";
const listeners = new Set<() => void>();

function initial(): IdeaState {
  return {
    request: emptyRequest(),
    precheck: null,
    acknowledged: false,
    recommendationId: null,
    recommendationIndex: null,
    differentiationTransfer: null,
    clarifyAnswers: [],
    inputMode: "quick",
    quickText: "",
    quickTitle: "",
    comparison: null,
    brief: null,
    priorityEvidence: [],
    similarChoices: {},
    choiceSources: {},
    planSig: null,
    originalPlan: null,
    planSource: "original",
    appliedChoices: null,
    appliedChoiceSources: null,
    policyDeferred: false,
    referenceIds: [],
    appliedReferenceIds: null,
    planRefSig: null,
  };
}

function load(): IdeaState {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return initial();
    const parsed = JSON.parse(raw) as Partial<IdeaState>;
    const loaded: IdeaState = { ...initial(), ...parsed, request: { ...emptyRequest(), ...(parsed.request ?? {}) } };
    // 출처 기록 전에 저장된 상태 — AI 기본 선택과 같은 값은 ai_prefill 로 본다 (ADR 0056)
    const defaults = (loaded.precheck as { default_choices?: SimilarChoice[] } | null)?.default_choices;
    if (parsed.choiceSources === undefined) loaded.choiceSources = inferSources(loaded.similarChoices, defaults);
    if (parsed.appliedChoiceSources === undefined && loaded.appliedChoices) loaded.appliedChoiceSources = inferSources(loaded.appliedChoices, defaults);
    return loaded;
  } catch {
    return initial();
  }
}

let state: IdeaState = load();

function persist() {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    /* ignore */
  }
  for (const l of listeners) l();
}

export function getIdea(): IdeaState {
  return state;
}

export function updateIdea(patch: Partial<IdeaState>): void {
  // 새 유사과제 확인 결과가 오면(① 에서 다시 확인) 이전 아이디어의 선택·과제안 상태를 비운다
  const fresh = patch.precheck !== undefined && patch.precheck !== state.precheck && !("similarChoices" in patch);
  state = fresh
    ? {
        ...state,
        similarChoices: {},
        choiceSources: {},
        planSig: null,
        originalPlan: null,
        planSource: "original",
        appliedChoices: null,
        appliedChoiceSources: null,
        referenceIds: [],
        appliedReferenceIds: null,
        planRefSig: null,
        plansStale: false,
        ...patch,
      }
    : { ...state, ...patch };
  persist();
}

export function updateRequest(patch: Partial<IdeaRequest>): void {
  state = { ...state, request: { ...state.request, ...patch } };
  persist();
}

export function resetIdea(): void {
  state = initial();
  persist();
}

export function useIdea(): IdeaState {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    getIdea,
    getIdea,
  );
}
