/** '핵심 문제' 카드 — 한 줄을 고친 뒤 서버에 보낼 카드(after)와 고친 항목(fields)을 만드는 순수 함수들 (ADR 0065).
 *  값만 바꾼다 — 제안자 수정 표시(origin·ai_value)와 그 항목에 기대는 것의 재계산은 서버가 한다(계약 3.2절). */
import type { CardField, CardText, ClassCode, ProblemCard } from "@/api/types-problem-card";

export type CardLineKey = "function" | "cause" | "contradiction" | "codes";
export const CARD_LINE_KEYS: CardLineKey[] = ["function", "cause", "contradiction", "codes"];

/** 서버 모델의 상한과 같다 (domain/models/problem_card.py) */
export const CARD_TEXT_MAX = 300;
export const CARD_CODE_MAX = 24;
export const CODE_LIMITS = { ipc: 3, science_class: 2 } as const;
export type CodeKind = keyof typeof CODE_LIMITS;

/** 고친 결과 — 바뀐 것이 없으면 null(서버를 부르지 않는다) */
export interface CardChange {
  after: ProblemCard;
  fields: CardField[];
}

const tidy = (v: string) => v.replace(/\s+/g, " ").trim().slice(0, CARD_TEXT_MAX);

export function changeFunction(card: ProblemCard, value: string): CardChange | null {
  const next = tidy(value);
  if (next === card.function_ko.value) return null;
  return { after: { ...card, function_ko: { ...card.function_ko, value: next } }, fields: ["function_ko"] };
}

export function changeCause(card: ProblemCard, value: string): CardChange | null {
  const next = tidy(value);
  const first = card.causes[0];
  if (next === (first?.value ?? "")) return null;
  const cause: CardText = first ? { ...first, value: next } : { value: next, origin: "user", basis: "추정", ai_value: "", needs_check: false };
  return { after: { ...card, causes: [cause, ...card.causes.slice(1)] }, fields: ["cause"] };
}

export function changeContradiction(card: ProblemCard, improve: string, worsen: string): CardChange | null {
  const a = tidy(improve);
  const b = tidy(worsen);
  if (a === card.contradiction.improve && b === card.contradiction.worsen) return null;
  return { after: { ...card, contradiction: { ...card.contradiction, improve: a, worsen: b } }, fields: ["contradiction"] };
}

export function normalizeCode(raw: string): string {
  return raw.replace(/[<>"\s]+/g, " ").trim().toUpperCase().slice(0, CARD_CODE_MAX);
}

/** 제안자가 더한 코드 — 확인은 서버가 한다 */
export function newCode(raw: string): ClassCode | null {
  const code = normalizeCode(raw);
  return code ? { code, label: "", origin: "user", verified: "unverified", count: null } : null;
}

const codeSig = (list: ClassCode[]) => list.map((c) => c.code).join("|");

export function changeCodes(card: ProblemCard, ipc: ClassCode[], science: ClassCode[]): CardChange | null {
  const fields: CardField[] = [];
  if (codeSig(ipc) !== codeSig(card.ipc)) fields.push("ipc");
  if (codeSig(science) !== codeSig(card.science_class)) fields.push("science_class");
  if (!fields.length) return null;
  return { after: { ...card, ipc, science_class: science }, fields };
}

/** 그 줄을 제안자가 고쳤는가 — 고친 줄은 '근거 있음/추정' 대신 '직접 고침' 을 보인다 */
export function lineByUser(card: ProblemCard, key: CardLineKey): boolean {
  if (key === "function") return card.function_ko.origin === "user";
  if (key === "cause") return card.causes[0]?.origin === "user";
  if (key === "contradiction") return card.contradiction.origin === "user";
  const codes = [...card.ipc, ...card.science_class];
  return codes.length > 0 && codes.every((c) => c.origin === "user");
}
