import type { CheckTarget } from "@/api/types";

/** target → 화면 경로. section:<key> → 초안 보기 앵커, sentence:<sid> → 초안 보기 + 근거 패널, route:<hint> → run 하위 경로 */
export function targetPath(runId: string, target: CheckTarget): string | null {
  if (!target) return null;
  const base = `/runs/${runId}`;
  if (target.startsWith("section:")) return `${base}/draft#sec-${target.slice("section:".length)}`;
  if (target.startsWith("sentence:")) return `${base}/draft?evidence=${encodeURIComponent(target.slice("sentence:".length))}`;
  const hint = target.slice("route:".length);
  const ROUTES: Record<string, string> = { evidence: "draft", draft: "draft", edit: "edit", "final-review": "final-review", final_review: "final-review", finalize: "finalize", versions: "versions" };
  return `${base}/${ROUTES[hint] ?? hint}`;
}

