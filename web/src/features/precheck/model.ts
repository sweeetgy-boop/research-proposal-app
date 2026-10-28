/** ② 유사과제 흐름의 화면 규칙 (순수 함수) — 서버 domain/rules/similar_choice 와 같은 규칙. */
import type {
  IdeaVersion,
  IdeaVersionKind,
  JudgmentLevel,
  PlanField,
  PlanRecommendation,
  PrecheckAlert,
  PrecheckRequest,
  SimilarChoice,
  SeriesView,
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

// ── ② v3 (ADR 0039): 판정 칸·기본 선택·선택 적용 ─────────────────────────
export const LEVEL_LABELS: Record<JudgmentLevel, string> = { blocking: "차단", near: "근접", low: "관련 낮음" };
const VERDICT_LEVEL: Record<string, JudgmentLevel> = { same: "blocking", partial: "near", different: "low" };

/** 판정 칸 — AI 판정(같다→차단·일부 겹침→근접·다르다→관련 낮음), 없으면 규칙 판정(차단·근접, "규칙 기준") */
export function levelOf(a: PrecheckAlert): { level: JudgmentLevel; label: string; basis: "ai" | "rule" } {
  const fromAi = a.judgment ? VERDICT_LEVEL[a.judgment] : undefined;
  if (fromAi) return { level: fromAi, label: LEVEL_LABELS[fromAi], basis: "ai" };
  const level: JudgmentLevel = a.blocking ? "blocking" : "near";
  return { level, label: LEVEL_LABELS[level], basis: "rule" };
}

/** AI "다르다" 행의 기본 [관련 없음] 을 선택이 없는 행에만 채운다 (제안자가 고른 값은 바꾸지 않는다) */
export function withDefaults(
  map: ChoiceMap,
  defaults: SimilarChoice[] | undefined,
  alerts: PrecheckAlert[],
): { map: ChoiceMap; added: number } {
  const next = { ...map };
  let added = 0;
  for (const d of defaults ?? []) {
    const alert = alerts.find((a) => a.doc_id === d.doc_id);
    if (alert && choiceOf(alert, next) === undefined) {
      next[d.doc_id] = d.choice;
      added += 1;
    }
  }
  return { map: next, added };
}

/** 선택 전체 서명 (유사함·관련 없음 모두) — [선택 적용] 뒤 바뀌었는지 */
export function fullSignature(map: ChoiceMap): string {
  return Object.keys(map)
    .sort()
    .map((k) => `${k}=${map[k]}`)
    .join("|");
}

export function choiceCounts(alerts: PrecheckAlert[], map: ChoiceMap): { similar: number; unrelated: number } {
  let similar = 0;
  let unrelated = 0;
  for (const a of alerts) {
    const c = choiceOf(a, map);
    if (c === "similar") similar += 1;
    else if (c === "unrelated") unrelated += 1;
  }
  return { similar, unrelated };
}

export function changedFields(before: Record<PlanField, string>, after: Record<PlanField, string>): PlanField[] {
  return PLAN_FIELDS.map((f) => f.key).filter((k) => (before[k] ?? "") !== (after[k] ?? ""));
}

// ── 같은 연작 한 줄 (ADR 0043) ─────────────────────────
/** 연작 행에 보일 자료원 이름 — 판마다 실린 자료원을 모은 것 (중복 없이) */
export function seriesSources(series: SeriesView): string {
  const names = new Set<string>();
  for (const m of series.members) for (const n of m.source_label.split(" · ")) if (n) names.add(n);
  return [...names].join(" · ");
}
