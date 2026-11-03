/** ② 관련 연구 목록으로 옮겨 가기 — 과제안 0건 안내의 [관련 연구로 이동] (ADR 0053) */

/** 관련 연구 제목 id (RelatedResearchList 의 h2) */
export const RELATED_RESEARCH_HEADING_ID = "related-research-heading";

/** 관련 연구 제목으로 스크롤하고 포커스를 옮긴다 */
export function focusRelatedResearch(): void {
  const el = document.getElementById(RELATED_RESEARCH_HEADING_ID);
  if (!el) return;
  el.scrollIntoView?.({ behavior: "smooth", block: "start" });
  el.focus({ preventScroll: true });
}
