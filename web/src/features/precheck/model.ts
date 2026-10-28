/** ② 유사과제 흐름의 화면 규칙 (순수 함수) — 서버 domain/rules/similar_choice 와 같은 규칙. */
import type {
  IdeaVersion,
  IdeaVersionKind,
  PlanField,
  PlanRecommendation,
  PrecheckAlert,
  PrecheckRequest,
  SimilarChoice,
  SimilarChoiceValue,
} from "@/api/types";
import { PLAN_FIELDS } from "@/api/types";

export type ChoiceMap = Record<string, SimilarChoiceValue>;

export const GATE_REASON = "차단 경보를 확인해 주세요 — 차단 행에서 [유사함]·[관련 없음] 을 고르거나 확인란에 표시하십시오.";
export const RELEASED_NOTE = "차단 과제를 모두 [관련 없음] 으로 골라 차단 경보를 풀었습니다.";
export const MAX_VERSIONS = 10;

export function choiceList(map: ChoiceMap): SimilarChoice[] {
  return Object.entries(map).map(([doc_id, choice]) => ({ doc_id, choice }));
}

export function choiceOf(alert: PrecheckAlert, map: ChoiceMap): SimilarChoiceValue | undefined {
  for (const id of [alert.doc_id, ...(alert.merged_ids ?? [])]) if (map[id]) return map[id];
  return undefined;
}

/** 차단 행 중 [관련 없음] 이 아닌 것이 있으면 차단 */
export function effectiveBlocking(alerts: PrecheckAlert[], map: ChoiceMap): boolean {
  return alerts.some((a) => a.blocking && choiceOf(a, map) !== "unrelated");
}

export function released(alerts: PrecheckAlert[], map: ChoiceMap): boolean {
  return alerts.some((a) => a.blocking) && !effectiveBlocking(alerts, map);
}

export function similarIds(alerts: PrecheckAlert[], map: ChoiceMap): string[] {
  return alerts.filter((a) => choiceOf(a, map) === "similar").map((a) => a.doc_id);
}

/** 과제안을 만든 시점의 선택과 지금 선택이 다른지 — [과제안 다시 만들기] 표시용 */
export function choicesSignature(map: ChoiceMap): string {
  return Object.keys(map)
    .filter((k) => map[k] === "similar")
    .sort()
    .join("|");
}

export function planFields(req: PrecheckRequest): Record<PlanField, string> {
  const out = {} as Record<PlanField, string>;
  for (const f of PLAN_FIELDS) out[f.key] = String((req as Record<string, unknown>)[f.key] ?? "");
  return out;
}

export function cardFields(card: PlanRecommendation, base: PrecheckRequest): Record<PlanField, string> {
  return {
    title_hint: card.title,
    goal: card.goal || base.goal,
    method: card.method || "",
    scope: card.scope || "",
    differentiation: card.differentiation,
  };
}

export function addVersion(
  versions: IdeaVersion[] | undefined,
  kind: IdeaVersionKind,
  fields: Partial<Record<PlanField, string>>,
  cardIndex?: number | null,
): IdeaVersion[] {
  const list = [...(versions ?? [])];
  const at = new Date().toISOString().slice(0, 19);
  const next: IdeaVersion = { kind, fields: { ...fields }, card_index: cardIndex ?? null, at };
  const out = [...list, next];
  return out.slice(-MAX_VERSIONS);
}

export function changedFields(before: Record<PlanField, string>, after: Record<PlanField, string>): PlanField[] {
  return PLAN_FIELDS.map((f) => f.key).filter((k) => (before[k] ?? "") !== (after[k] ?? ""));
}
