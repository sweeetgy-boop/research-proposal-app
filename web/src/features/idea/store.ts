/** ①~③ 사이에 들고 다니는 제안자 입력. 새로고침에 견디도록 sessionStorage 에 둔다
 *  (아이디어 본문뿐 — 개인정보·토큰 없음). */
import { useSyncExternalStore } from "react";
import type { BriefOut, ComparisonOut, DifferentiationTransferIn, PrecheckOut, ProposalRequest } from "@/api/types";
import { emptyRequest } from "@/lib/validation";

export interface IdeaState {
  request: ProposalRequest;
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
  };
}

function load(): IdeaState {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return initial();
    const parsed = JSON.parse(raw) as Partial<IdeaState>;
    return { ...initial(), ...parsed, request: { ...emptyRequest(), ...(parsed.request ?? {}) } };
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
  state = { ...state, ...patch };
  persist();
}

export function updateRequest(patch: Partial<ProposalRequest>): void {
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
