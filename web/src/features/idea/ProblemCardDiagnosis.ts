/** ① 문제 정의 카드 진단을 뒤에서 돌리는 훅과 줄 수정 반영 (ADR 0065, 계약 5절).
 *  - 네 칸이 모두 찬 뒤 입력이 멈추면(디바운스) 네 칸 서명이 진단한 서명과 다를 때 1회. 간편 입력에서 채웠을 때는 바로(run).
 *  - 화면을 막지 않는다. 꺼짐·실패·오류(404·5xx·네트워크)는 모두 "카드 없음" — 알림 없이 종전 화면 그대로.
 *  - 입력이 바뀌면 진행 중 호출은 끊고, 재진단에는 지금 카드를 previous 로 실어 제안자가 고친 항목을 지킨다. */
import * as React from "react";
import { diagnoseProblem, editProblemCard } from "@/api/problemCard";
import type { DiagnoseOut } from "@/api/types-problem-card";
import type { CardChange } from "./ProblemCardModel";
import { fourSignature, getIdea, updateIdea, updateRequest, type IdeaState } from "./store";

export const DIAGNOSE_DEBOUNCE_MS = 1500;

const four = (r: IdeaState["request"]) => ({
  title_hint: r.title_hint ?? "",
  current_state: r.current_state,
  root_cause: r.root_cause,
  limitation: r.limitation,
  goal: r.goal,
});

/** ② 로 넘어간 뒤(유사과제 확인 결과가 있음)에는 들고 다니는 입력의 카드도 같이 맞춘다 — 과제안 다시 만들기·보강 질문·초안이 새 카드를 쓴다 */
function syncCarried(): void {
  const now = getIdea();
  if (!now.precheck) return;
  const card = now.problemCard && now.cardSig === fourSignature(now.request) ? now.problemCard : undefined;
  if (now.request.problem_card !== card) updateRequest({ problem_card: card });
}

/** [다음] 때 요청에 실을 카드 — 지금 네 칸으로 진단을 마친 카드만. 아직이거나 실패·꺼짐이면 null(카드 없이 진행) */
export function usableCard(state: IdeaState = getIdea()) {
  const sig = fourSignature(state.request);
  return state.problemCard && sig !== null && state.cardSig === sig ? state.problemCard : null;
}

export interface ProblemDiagnosis {
  /** 진단 호출이 돌고 있다 */
  pending: boolean;
  /** 카드가 있는데 네 칸이 그 뒤 바뀌었다 */
  changed: boolean;
  /** 네 칸 중 빈 칸이 있어 다시 정리할 수 없다 */
  incomplete: boolean;
  /** 지금 바로 진단(네 칸이 찼고 아직 진단하지 않은 입력일 때만) */
  run: () => void;
  /** [다시 정리] — 고정·캐시를 건너뛰고 새로 진단한다. 실패하면 지금 카드를 그대로 둔다 */
  refresh: () => void;
  /** 진행 중 호출을 끊는다 — [다음] 은 기다리지 않는다 */
  cancel: () => void;
}

export function useProblemDiagnosis(idea: IdeaState, active: boolean): ProblemDiagnosis {
  const [pending, setPending] = React.useState(false);
  const flight = React.useRef<{ ctl: AbortController; sig: string } | null>(null);

  const cancel = React.useCallback(() => {
    if (!flight.current) return;
    flight.current.ctl.abort();
    flight.current = null;
    setPending(false);
  }, []);

  const start = React.useCallback((refresh: boolean) => {
    const now = getIdea();
    const sig = fourSignature(now.request);
    if (!sig || flight.current?.sig === sig) return;
    if (!refresh && sig === now.cardSig) return;
    flight.current?.ctl.abort();
    const mine = { ctl: new AbortController(), sig };
    flight.current = mine;
    setPending(true);
    void (async () => {
      let out: DiagnoseOut | null = null;
      try {
        out = await diagnoseProblem(
          { ...four(now.request), ...(now.problemCard ? { previous: now.problemCard } : {}), ...(refresh ? { refresh: true } : {}) },
          { signal: mine.ctl.signal },
        );
      } catch {
        out = null; // 경로 없음·서버 오류·네트워크 — 카드 없이 간다
      }
      if (mine.ctl.signal.aborted || flight.current !== mine) return;
      flight.current = null;
      setPending(false);
      if (out?.status === "ok" && out.card && out.lines) {
        // 다시 정리한 카드는 이미 받은 과제안의 문제 정의와 다를 수 있다 → ② 에 [과제안 다시 만들기] 표시만
        const stale = refresh && !!(getIdea().precheck as { recommendations?: unknown } | null)?.recommendations;
        updateIdea({
          problemCard: out.card,
          cardLines: out.lines,
          cardSignals: out.signal_labels ?? [],
          cardSig: sig,
          cardReused: out.reused ?? null,
          ...(stale ? { plansStale: true } : {}),
        });
      } else if (refresh) {
        return; // 다시 정리에 실패하면 지금 카드를 그대로 둔다
      } else {
        updateIdea({ problemCard: null, cardLines: null, cardSignals: [], cardSig: sig, cardReused: null });
      }
      syncCarried();
    })();
  }, []);
  const run = React.useCallback(() => start(false), [start]);
  const refresh = React.useCallback(() => start(true), [start]);

  const sig = fourSignature(idea.request);
  React.useEffect(() => {
    // 입력이 바뀌었거나 화면이 [다음] 으로 넘어가는 중이면 옛 진단은 버린다
    if (flight.current && (flight.current.sig !== sig || !active)) cancel();
    if (!active || !sig || sig === idea.cardSig || flight.current?.sig === sig) return;
    const t = window.setTimeout(run, DIAGNOSE_DEBOUNCE_MS);
    return () => window.clearTimeout(t);
  }, [active, sig, idea.cardSig, run, cancel]);
  React.useEffect(() => () => flight.current?.ctl.abort(), []);

  return { pending, changed: !!idea.problemCard && sig !== idea.cardSig, incomplete: sig === null, run, refresh, cancel };
}

/** 한 줄 [적용] — diagnose/edit 응답의 카드·4줄로 갈아 끼운다. 실패하면 던진다(카드가 편집을 연 채 안내).
 *  plans_stale 이고 이미 받은 과제안이 있으면 ② 에 [과제안 다시 만들기] 한 줄을 보이게 표시만 한다(자동 실행 없음). */
export async function applyCardEdit(change: CardChange): Promise<void> {
  const before = getIdea();
  if (!before.problemCard) return;
  const out = await editProblemCard({ request: four(before.request), before: before.problemCard, after: change.after, fields: change.fields });
  const now = getIdea();
  const hasPlans = !!(now.precheck as { recommendations?: unknown } | null)?.recommendations;
  updateIdea({
    problemCard: out.card,
    cardLines: out.lines,
    plansStale: !!now.plansStale || (out.plans_stale && hasPlans),
  });
  syncCarried();
}
