/** 정책적 중요도 작성안 — 순수 함수 (서버 domain/rules/policy_cards 와 같은 규칙: 합치기·직접 수정·문장 나누기). */
import type { PolicyCard, PolicyChoice, PolicySentence } from "@/api/types";

const squash = (s: string) => s.replace(/\s+/g, "");
const BULLET = /^\s*(?:[○●◦•·\-–—]|\d+[.)])\s*/;
export const MAX_CHOICE_SENTENCES = 6;

export function choiceFromCard(card: PolicyCard): PolicyChoice {
  return { mode: "card", card_ids: [card.id], sentences: [...card.sentences], sources: [...card.sources] };
}

/** 두 안 합치기 — 문장은 a 다음 b(같은 문장은 한 번), 출처는 합친다 */
export function mergeCards(a: PolicyCard, b: PolicyCard): PolicyChoice {
  const sentences: PolicySentence[] = [];
  for (const s of [...a.sentences, ...b.sentences]) {
    if (!sentences.some((x) => squash(x.text) === squash(s.text))) sentences.push(s);
  }
  const ids = new Set(a.sources.map((s) => s.chunk_id));
  return {
    mode: "merged",
    card_ids: [a.id, b.id],
    sentences: sentences.slice(0, MAX_CHOICE_SENTENCES),
    sources: [...a.sources, ...b.sources.filter((s) => !ids.has(s.chunk_id))],
  };
}

export function splitLines(text: string): string[] {
  return text
    .split(/\n+/)
    .map((l) => l.replace(BULLET, "").trim())
    .filter(Boolean)
    .slice(0, MAX_CHOICE_SENTENCES);
}

/** 고른 안을 고친 글 → 제안자 글. 원래 문장과 같은 줄은 근거를 이어받는다. base 가 없으면 직접 작성(manual). */
export function editedChoice(base: PolicyChoice | null, text: string): PolicyChoice {
  const prior = new Map((base?.sentences ?? []).map((s) => [squash(s.text), s] as const));
  return {
    mode: base && base.mode !== "manual" && base.mode !== "none" ? "edited" : "manual",
    card_ids: base?.card_ids ?? [],
    sentences: splitLines(text).map((t) => prior.get(squash(t)) ?? { text: t, evidence: [] }),
    sources: base?.sources ?? [],
  };
}

export const NONE_CHOICE: PolicyChoice = { mode: "none", sentences: [], sources: [] };

export function choiceText(choice: PolicyChoice | null): string {
  return (choice?.sentences ?? []).map((s) => `○ ${s.text}`).join("\n");
}

export const MODE_LABEL: Record<PolicyChoice["mode"], string> = {
  card: "작성안 그대로",
  merged: "두 안 합침",
  edited: "고른 안을 고침",
  manual: "직접 작성",
  none: "정책 근거 없음으로 진행",
};

/** 이미 본 문서 id — [다른 안 보기] 때 뺀다 */
export function seenDocs(cards: PolicyCard[], prev: string[] = []): string[] {
  const out = [...prev];
  for (const c of cards) for (const s of c.sources) if (!out.includes(s.doc_id)) out.push(s.doc_id);
  return out;
}

/** ④ 대화상자 "직접 입력" — 고른 안 뒤에 줄마다 한 문장으로 덧붙인다(같은 문장은 한 번, 근거 없음).
 *  "정책 근거 없음" 은 그대로 둔다. 직접 입력만 있으면 editedChoice(null, text) 로 직접 작성. */
export function withManual(choice: PolicyChoice, text: string): PolicyChoice {
  const extra = splitLines(text);
  if (!extra.length || choice.mode === "none") return choice;
  const sentences = [...choice.sentences];
  for (const t of extra) if (!sentences.some((x) => squash(x.text) === squash(t))) sentences.push({ text: t, evidence: [] });
  return { ...choice, mode: choice.mode === "manual" ? "manual" : "edited", sentences: sentences.slice(0, MAX_CHOICE_SENTENCES) };
}
