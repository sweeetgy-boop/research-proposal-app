/** 유사과제 티어 라벨 — 서버 tier_label 이 우선, 없거나 비면 여기서 보충 (domain/rules/overlap._TIER_LABEL 과 같은 값). */
export const TIER_LABELS: Record<string, string> = {
  own: "사내",
  national_rnd: "국가R&D 과제",
  domestic_rail: "국내 철도",
  external: "외부",
};

export const NATIONAL_RND = "national_rnd";

export function tierLabel(a: { tier: string; tier_label?: string | null }): string {
  return a.tier_label || TIER_LABELS[a.tier] || a.tier;
}
