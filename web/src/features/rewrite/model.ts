import type { RewriteOut } from "@/api/types";

/** 후보 행 → 기본 선택: 후보가 있는 행 전부 (보존 문장은 고르지 않아도 남는다) */
export function defaultChosen(out: RewriteOut): number[] {
  return out.rows.filter((r) => r.candidate && !r.candidate.preserved).map((r) => r.index);
}
