/** ④ 직접 수정 편집 모델 — 순수 함수. 문장 단위 선택(keep/use_revision/manual/delete/insert_after)과
 *  섹션 통문 편집을 EditRequest(저장)·WorkingIn(임시 저장)·미리보기 텍스트로 바꾼다. */
import type { EditRequest, ReviewComment, SentenceEdit, VersionSection, WorkingIn } from "@/api/types";

export type Action = "keep" | "use_revision" | "manual" | "delete" | "insert_after";

export interface SentenceState {
  action: Action;
  text?: string; // manual
  commentId?: string; // use_revision
  inserted?: string; // insert_after 새 문장
}

export interface EditState {
  sentences: Record<string, SentenceState>; // sentence_id → 상태
  sectionText: Record<string, string>; // 섹션 통문 편집 (있으면 문장 편집보다 우선)
  note: string;
  doneAnnotations: string[];
}

export const emptyEditState = (): EditState => ({ sentences: {}, sectionText: {}, note: "", doneAnnotations: [] });

/** 문장별로 쓸 수 있는 수정안(usable) — sentence_id → 의견 목록 */
export function usableRevisions(comments: ReviewComment[] | undefined): Map<string, ReviewComment[]> {
  const m = new Map<string, ReviewComment[]>();
  for (const c of comments ?? []) {
    if (!c.usable || !c.sentence_id || !c.revised_text) continue;
    const arr = m.get(c.sentence_id) ?? [];
    arr.push(c);
    m.set(c.sentence_id, arr);
  }
  return m;
}

export function isDirty(state: EditState): boolean {
  if (Object.keys(state.sectionText).length) return true;
  if (state.doneAnnotations.length) return true;
  return Object.values(state.sentences).some((s) => s.action !== "keep" || (s.inserted ?? "").trim());
}

/** 저장 요청 — 바뀐 것만 보낸다. */
export function toEditRequest(state: EditState, baseVersion: number, revisions: Map<string, ReviewComment[]>): EditRequest {
  const sentences: SentenceEdit[] = [];
  for (const [sid, s] of Object.entries(state.sentences)) {
    const section = sid.split(":")[1] ?? "";
    if (state.sectionText[section] !== undefined) continue; // 통문 편집이 우선
    if (s.action === "use_revision") {
      const commentId = s.commentId ?? revisions.get(sid)?.[0]?.id;
      sentences.push({ sentence_id: sid, action: "use_revision", comment_id: commentId ?? null });
    } else if (s.action === "manual" && (s.text ?? "").trim()) {
      sentences.push({ sentence_id: sid, action: "manual", text: s.text!.trim() });
    } else if (s.action === "delete") {
      sentences.push({ sentence_id: sid, action: "delete" });
    }
    if ((s.inserted ?? "").trim()) {
      sentences.push({ sentence_id: sid, action: "insert_after", text: s.inserted!.trim() });
    }
  }
  return {
    sentences,
    sections: Object.entries(state.sectionText).map(([section, text]) => ({ section, text, texts: [], order: null })),
    note: state.note.slice(0, 200),
    base_version: baseVersion,
    done_annotations: state.doneAnnotations,
  };
}

/** 편집 결과 미리보기 텍스트 — 섹션별 문장 목록(임시 저장 본문과 같다). */
export function previewTexts(sections: VersionSection[], state: EditState, revisions: Map<string, ReviewComment[]>): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const sec of sections) {
    if (state.sectionText[sec.key] !== undefined) {
      out[sec.key] = splitSentences(state.sectionText[sec.key] ?? "");
      continue;
    }
    const texts: string[] = [];
    for (const s of sec.sentences) {
      const st = state.sentences[s.sentence_id];
      if (!st || st.action === "keep") texts.push(s.text);
      else if (st.action === "manual") texts.push((st.text ?? "").trim() || s.text);
      else if (st.action === "use_revision") {
        const c = (st.commentId && revisions.get(s.sentence_id)?.find((x) => x.id === st.commentId)) || revisions.get(s.sentence_id)?.[0];
        texts.push(c?.revised_text ?? s.text);
      }
      // delete → 없음
      if (st?.inserted?.trim()) texts.push(st.inserted.trim());
    }
    out[sec.key] = texts;
  }
  return out;
}

export function toWorking(sections: VersionSection[], state: EditState, baseVersion: number, revisions: Map<string, ReviewComment[]>): WorkingIn {
  const texts = previewTexts(sections, state, revisions);
  return {
    sections: Object.entries(texts).map(([section, t]) => ({ section, texts: t })),
    note: state.note.slice(0, 200),
    base_version: baseVersion,
  };
}

/** 임시 저장(working)을 편집 상태로 되돌린다 — 섹션 통문으로 복원(문장 단위 선택은 복원하지 않는다). */
export function fromWorking(working: { sections: { section: string; texts?: string[]; text?: string }[]; note: string }, sections: VersionSection[]): EditState {
  const state = emptyEditState();
  state.note = working.note ?? "";
  for (const w of working.sections) {
    const original = sections.find((s) => s.key === w.section);
    const texts = w.texts ?? (w.text ? splitSentences(w.text) : []);
    const same = original && original.sentences.length === texts.length && original.sentences.every((s, i) => s.text === texts[i]);
    if (!same) state.sectionText[w.section] = texts.join("\n");
  }
  return state;
}

/** 통문 → 문장. 줄바꿈 우선, 없으면 종결어미 뒤에서 나눈다 (백엔드 split_sentences 의 근사). */
export function splitSentences(text: string): string[] {
  const lines = text
    .split(/\n+/)
    .map((l) => l.trim())
    .filter(Boolean);
  const out: string[] = [];
  for (const line of lines) {
    const parts = line.split(/(?<=[.。!?])\s+(?=\S)/).map((p) => p.trim()).filter(Boolean);
    out.push(...(parts.length ? parts : [line]));
  }
  return out;
}

export function countChanges(state: EditState): number {
  let n = Object.keys(state.sectionText).length;
  for (const s of Object.values(state.sentences)) {
    if (s.action !== "keep") n += 1;
    if ((s.inserted ?? "").trim()) n += 1;
  }
  return n;
}
