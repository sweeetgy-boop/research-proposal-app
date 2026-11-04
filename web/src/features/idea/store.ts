/** ①~③ 사이에 들고 다니는 제안자 입력. 새로고침에 견디도록 sessionStorage 에 둔다
 *  (아이디어 본문뿐 — 개인정보·토큰 없음). */
import { useSyncExternalStore } from "react";
import type { BriefOut, ChoiceSource, ComparisonOut, DifferentiationTransferIn, PlanField, PrecheckOut, PrecheckRequest, SimilarChoice, SimilarChoiceValue } from "@/api/types";
import { inferSources } from "@/features/precheck/model";
import { emptyRequest } from "@/lib/validation";

export interface IdeaState {
  request: PrecheckRequest;
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
        ...patch,
      }
    : { ...state, ...patch };
  persist();
}

export function updateRequest(patch: Partial<PrecheckRequest>): void {
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
