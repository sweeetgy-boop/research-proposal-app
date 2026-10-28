/** 문서 표시 — 화면에 내부 문서 번호(own:…·alio:sum-…·ntis:…·f:method:t1 …)를 내보내지 않는다 (ADR 0040, 레인 B).
 *  "제목 · 자료원 이름(한국어)" 을 보이고, 누르면 근거 패널(요약 + 원문 링크)을 연다 — components/DocRef.tsx.
 *  서버 규칙은 src/rra/domain/rules/doc_refs.py (SOURCE_NAMES 는 같은 값이어야 한다 — tests/domain/test_doc_refs.py 가 맞춘다). */

/** 자료원 키 → 한국어 이름 (domain/rules/doc_refs.SOURCE_NAMES 와 같은 값) */
export const SOURCE_NAMES: Record<string, string> = {
  own: "사내 과제",
  alio: "알리오 공시",
  ntis: "NTIS 국가R&D",
  scienceon: "ScienceON",
  openalex: "OpenAlex 논문",
  kipris_kr: "KIPRIS 국내 특허",
  kipris_intl: "KIPRIS 해외 특허",
  korail_web: "공사 홈페이지",
  molit: "국토교통부",
  rnd_notice: "R&D 공고",
  g2b: "나라장터",
  bai: "감사원",
  mofe: "기획재정부",
  datago: "공공데이터포털",
};
export const UNKNOWN_SOURCE = "수집 자료";
export const UNTITLED = "제목 없는 자료";

/** 화면이 쓰는 문서 표시 정보 — 서버 뷰(citations·evidence_refs·policy suggestions …)가 싣는 모양 */
export interface DocRefData {
  doc_id?: string;
  /** 문장 근거 id (chunk_id 또는 doc_id) */
  id?: string;
  title?: string | null;
  source?: string | null;
  source_label?: string | null;
  /** 원문 링크 — 공개 문서만 */
  url?: string | null;
  /** 근거 패널 요약(발췌·인용) */
  summary?: string | null;
  live?: boolean;
}

const SOURCE_KEYS = Object.keys(SOURCE_NAMES).sort((a, b) => b.length - a.length).join("|");
/** 문서·청크 번호 */
export const DOC_ID_RE = new RegExp(`\\b(?:${SOURCE_KEYS}):[A-Za-z0-9_\\-.:/]*[A-Za-z0-9_\\-](?:#\\d+)?`, "g");
/** 공개 요약 번호 (sum-0f3a…) */
export const SUM_ID_RE = /\bsum-[0-9a-f]{6,}(?:#\d+)?/g;
/** 그림 번호 f:<섹션>:<n> / f:<섹션>:t<n> */
export const FIGURE_ID_RE = /(?:(?:그림|figure)\s*)?\bf:([a-z_]+):(t?)(\d+)\b/g;
/** 문장 번호 s:<섹션>:<n> */
export const SENTENCE_ID_RE = /\bs:([a-z_]+):(\d+)\b/g;
const WRAPPED_RE = new RegExp(
  `[\\[(（]\\s*(?:(?:근거|출처|문서|자료|doc_id|evidence)\\s*[:：]\\s*)?(?:(?:${SOURCE_KEYS}):[^\\])）]*|sum-[0-9a-f]{6,}[^\\])）]*)[\\])）]`,
  "g",
);

export function sourceOf(docId: string | null | undefined): string {
  if (!docId) return "";
  const i = docId.indexOf(":");
  return i > 0 ? docId.slice(0, i) : "";
}

export function sourceName(source: string | null | undefined): string {
  return (source && SOURCE_NAMES[source]) || UNKNOWN_SOURCE;
}

/** 표시 제목 — 번호를 제목 대신 보이지 않는다 */
export function refTitle(ref: DocRefData | null | undefined): string {
  const t = (ref?.title ?? "").trim();
  return t && !hasInternalId(t) ? t : UNTITLED;
}

export function refSource(ref: DocRefData | null | undefined): string {
  return ref?.source_label || sourceName(ref?.source || sourceOf(ref?.doc_id ?? ref?.id));
}

/** 근거 id → 표시 정보 (citations 에서 찾고, 없으면 자료원 이름만) */
export function docRef(id: string, refs: readonly DocRefData[] = []): DocRefData {
  const base = id.split("#")[0] ?? id;
  const hit = refs.find((r) => r.id === id) ?? refs.find((r) => r.doc_id === id || r.doc_id === base || r.id === base);
  if (hit) return { ...hit, id };
  return { id, doc_id: base, title: null, source: sourceOf(base), source_label: sourceName(sourceOf(base)) };
}

/** id → 제목 표 (chunk_id·doc_id 둘 다) */
export function titleMap(refs: readonly DocRefData[]): Map<string, string> {
  const m = new Map<string, string>();
  for (const r of refs) {
    if (!r.title) continue;
    for (const k of [r.id, r.doc_id]) if (k && !m.has(k)) m.set(k, r.title);
  }
  return m;
}

/** 글에 섞인 내부 번호 → 「제목」(아는 문서) 또는 "관련 자료". 그림 → "<섹션> 그림 n", 문장 → "<섹션> 문장 n".
 *  서버 replace_internal_ids 와 같은 규칙 — 서버가 놓친 것을 화면에서 한 번 더 막는다. */
export function replaceDocIds(text: string | null | undefined, refs: readonly DocRefData[] = [], sectionTitle?: (key: string) => string): string {
  if (!text) return "";
  const titles = titleMap(refs);
  const titleFor = (id: string): string | undefined => {
    const base = id.split("#")[0] ?? id;
    return titles.get(id) ?? titles.get(base) ?? (id.startsWith("sum-") ? (titles.get(`alio:${id}`) ?? titles.get(`alio:${base}`)) : undefined);
  };
  const sec = (k: string) => (sectionTitle ? sectionTitle(k) : "");
  let out = text.replace(WRAPPED_RE, (m) => {
    const found = m.match(new RegExp(DOC_ID_RE.source)) ?? m.match(new RegExp(SUM_ID_RE.source));
    const t = found ? titleFor(found[0]) : undefined;
    return t ? `「${t}」` : "";
  });
  out = out.replace(DOC_ID_RE, (m) => {
    const t = titleFor(m);
    return t ? `「${t}」` : "관련 자료";
  });
  out = out.replace(SUM_ID_RE, (m) => {
    const t = titleFor(m);
    return t ? `「${t}」` : "관련 자료";
  });
  out = out.replace(FIGURE_ID_RE, (_m, s: string, t: string, n: string) => `${sec(s)} ${t ? "분석 기법 그림" : "그림"} ${n}`.trim());
  out = out.replace(SENTENCE_ID_RE, (_m, s: string, n: string) => `${sec(s)} 문장 ${Number(n) + 1}`.trim());
  return out.replace(/[ \t]{2,}/g, " ").replace(/\s+([.,)])/g, "$1").trim();
}

/** 내부 번호가 남아 있는가 (e2e helpers-text 의 expectNoInternalIds 와 같은 기준) */
export function hasInternalId(text: string | null | undefined): boolean {
  if (!text) return false;
  return [DOC_ID_RE, SUM_ID_RE, FIGURE_ID_RE, SENTENCE_ID_RE].some((re) => new RegExp(re.source).test(text));
}
