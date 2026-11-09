/** ② 유사과제 흐름의 화면 규칙 (순수 함수) — 서버 domain/rules/similar_choice 와 같은 규칙. */
import type {
  ChoiceSource,
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
import type { RecommendMode } from "@/api/types-novel";

export type ChoiceMap = Record<string, SimilarChoiceValue>;
/** doc_id → 선택의 출처 (ADR 0056). ChoiceMap 과 같은 키 */
export type SourceMap = Record<string, ChoiceSource>;

export const GATE_REASON = "차단 경보를 확인해 주세요 — 차단 행에서 [유사함]·[관련 없음] 을 고르거나 확인란에 표시하십시오.";
export const RELEASED_NOTE = "차단 과제를 모두 [관련 없음] 으로 골라 차단 경보를 풀었습니다.";
export const MAX_VERSIONS = 10;

/** 서버로 보내는 선택 목록 — 행마다 출처(source)를 함께. 출처가 없는 키는 user (서버 기본값과 같다, ADR 0056) */
export function choiceList(map: ChoiceMap, sources: SourceMap): SimilarChoice[] {
  return Object.entries(map).map(([doc_id, choice]) => ({ doc_id, choice, source: sources[doc_id] ?? "user" }));
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

/** 과제안이 실제로 쓴 [유사함] 서명 — 선택이 없는 행은 서버처럼 AI 기본 선택을 따른다 (ADR 0054).
 *  처음 과제안은 빈 선택으로 요청되고 서버가 기본 선택([유사함])으로 만든다 — 빈 선택 서명("")으로 적으면
 *  그 행을 [관련 없음] 으로 바꿔 [선택 적용] 해도 서명이 같아 과제안을 다시 받지 않았다 (2026-11-05, ADR 0057 통합). */
export function planSignature(map: ChoiceMap, defaults: SimilarChoice[] | undefined, alerts: PrecheckAlert[]): string {
  return choicesSignature(withDefaults(map, defaults, alerts).map);
}

/** 서버가 고를 과제안 갈래 (ADR 0057, 서버 `similar_rows.recommend_mode` 와 같은 규칙) — [유사함] 0건(선택 없는 행은 AI 기본
 *  선택) AND 차단 없음(차단 게이트는 제안자 선택만 — 미리 고른 값은 풀지 않는다)이면 novel, 아니면 differentiate. */
export function expectedMode(map: ChoiceMap, defaults: SimilarChoice[] | undefined, alerts: PrecheckAlert[]): RecommendMode {
  const effective = withDefaults(map, defaults, alerts).map;
  return similarIds(alerts, effective).length === 0 && !effectiveBlocking(alerts, map) ? "novel" : "differentiate";
}

/** 과제안을 만든 기준의 열쇠 = 갈래 + [유사함] 서명. 차단 행만 [관련 없음] 으로 바꿔 유사함 집합은 그대로인데 갈래가
 *  novel 로 바뀌는 경우(2026-11-09 레인 B)도 잡는다 — 이 열쇠가 다르면 [선택 적용] 이 과제안을 다시 받는다. */
export function planKey(map: ChoiceMap, defaults: SimilarChoice[] | undefined, alerts: PrecheckAlert[]): string {
  return `${expectedMode(map, defaults, alerts)}:${planSignature(map, defaults, alerts)}`;
}

/** 지금 화면의 과제안(mode 가 없으면 differentiate)이 지금 선택으로 계산한 갈래와 다른가 — 다르면 [더 만들기]·카드 적용 대신
 *  과제안을 새로 받는다(서버도 같은 경우 409 code=mode_changed 를 낸다). */
export function modeMismatch(rec: object | null | undefined, map: ChoiceMap, defaults: SimilarChoice[] | undefined, alerts: PrecheckAlert[]): boolean {
  if (!rec) return false;
  const { mode, novelty_reverted } = rec as { mode?: RecommendMode; novelty_reverted?: boolean };
  if (!mode) return false; // 갈래를 모르는 응답(옛 서버) — 서버 판정에 맡긴다
  const expected = expectedMode(map, defaults, alerts);
  // 넓은 검색에서 새 행이 걸려 서버가 novel 을 차별화로 되돌린 과제안(ADR 0057)은 novel 입력에 대한 서버의 답이다 — 전환 아님
  if (mode === "differentiate" && expected === "novel" && novelty_reverted) return false;
  return mode !== expected;
}

export const MODE_CHANGED_CODE = "mode_changed";

/** 서버 problem+json 이 갈래 전환(409 code=mode_changed)인가 */
export function isModeChanged(err: unknown): boolean {
  return !!err && typeof err === "object" && (err as { problem?: { code?: string } }).problem?.code === MODE_CHANGED_CODE;
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

/** 서버 기본 선택(ADR 0054 — AI 같다·일부 겹침 → [유사함], 다르다 → [관련 없음])을 선택이 없는 행에만 채운다
 *  (제안자가 고른 값은 바꾸지 않는다). 서버도 선택 없는 행에 같은 기본 선택을 쓰므로 건수가 서버와 같다. */
export function withDefaults(
  map: ChoiceMap,
  defaults: SimilarChoice[] | undefined,
  alerts: PrecheckAlert[],
  sources: SourceMap = {},
): { map: ChoiceMap; sources: SourceMap; added: number; addedSimilar: number; addedUnrelated: number } {
  const next = { ...map };
  const nextSources = { ...sources };
  let addedSimilar = 0;
  let addedUnrelated = 0;
  for (const d of defaults ?? []) {
    const alert = alerts.find((a) => a.doc_id === d.doc_id);
    if (alert && choiceOf(alert, next) === undefined) {
      next[d.doc_id] = d.choice;
      nextSources[d.doc_id] = "ai_prefill"; // 미리 고른 값 — 제안자가 바꾸기 전까지 ai_prefill (ADR 0056)
      if (d.choice === "similar") addedSimilar += 1;
      else addedUnrelated += 1;
    }
  }
  return { map: next, sources: nextSources, added: addedSimilar + addedUnrelated, addedSimilar, addedUnrelated };
}

/** 행의 서버 기본 선택 (없으면 undefined) — 선택을 지우면 이 값으로 돌아간다 (서버도 선택 없는 행은 기본 선택) */
export function defaultChoiceOf(alert: PrecheckAlert, defaults: SimilarChoice[] | undefined): SimilarChoiceValue | undefined {
  const ids = [alert.doc_id, ...(alert.merged_ids ?? [])];
  return (defaults ?? []).find((d) => ids.includes(d.doc_id))?.choice;
}

/** 행 하나의 선택을 바꾼다 (value = null 이면 지움) — 선택과 출처를 함께 (ADR 0056).
 *  - 묶음 행(같은 제목·같은 연작, ADR 0043)의 선택은 행 하나 — 구성원 doc_id 로 남은 옛 선택·출처는 지운다.
 *  - 지우면 AI 기본 선택으로 돌아간다(서버도 선택 없는 행은 기본 선택으로 센다, ADR 0054) — 출처는 ai_prefill.
 *  - 고른 값이 AI 기본 선택과 같으면 ai_prefill(미리 고른 값을 다시 누른 것은 사람 판단으로 세지 않는다),
 *    다르거나 기본 선택이 없는 행이면 user. */
export function chooseRow(
  map: ChoiceMap,
  sources: SourceMap,
  row: PrecheckAlert | undefined,
  docId: string,
  value: SimilarChoiceValue | null,
  defaults: SimilarChoice[] | undefined,
): { map: ChoiceMap; sources: SourceMap } {
  const next = { ...map };
  const nextSources = { ...sources };
  for (const id of row?.merged_ids ?? []) {
    delete next[id];
    delete nextSources[id];
  }
  const prefill = row ? defaultChoiceOf(row, defaults) : undefined;
  const chosen = value ?? prefill;
  if (chosen) {
    next[docId] = chosen;
    nextSources[docId] = prefill !== undefined && chosen === prefill ? "ai_prefill" : "user";
  } else {
    delete next[docId];
    delete nextSources[docId];
  }
  return { map: next, sources: nextSources };
}

/** 출처를 모르는 선택(이 기능 전에 저장된 화면 상태)의 출처 추정 — AI 기본 선택과 같은 값이면 ai_prefill, 아니면 user.
 *  지금 규칙(기본 선택과 같은 값 = ai_prefill)과 같다. */
export function inferSources(map: ChoiceMap, defaults: SimilarChoice[] | undefined): SourceMap {
  const byId = new Map((defaults ?? []).map((d) => [d.doc_id, d.choice] as const));
  const out: SourceMap = {};
  for (const [id, c] of Object.entries(map)) out[id] = byId.get(id) === c ? "ai_prefill" : "user";
  return out;
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

// ── 참고 논문 (ADR 0053) ─────────────────────────
/** ② 관련 연구에서 [차별화에 참고] 로 고를 수 있는 최대 건수 — 서버도 5 를 넘으면 422 */
export const MAX_REFERENCES = 5;
export const REFERENCE_LIMIT_NOTE = "참고 논문은 5건까지 고를 수 있습니다. 다른 자료를 고르려면 하나를 해제하십시오.";

/** 참고 논문 선택 서명 — 순서와 상관없이 같은 묶음이면 같다 ('선택이 바뀌었습니다'·과제안 다시 만들기 권유용) */
export function referenceSignature(ids: readonly string[] | null | undefined): string {
  return [...new Set(ids ?? [])].sort().join("|");
}

/** 체크/해제 — 고른 순서를 지키고(비교표 열 순서), 다섯 건이 차 있으면 더 넣지 않는다 */
export function toggleReference(ids: readonly string[], docId: string, on: boolean): string[] {
  if (!on) return ids.filter((x) => x !== docId);
  if (ids.includes(docId) || ids.length >= MAX_REFERENCES) return [...ids];
  return [...ids, docId];
}
