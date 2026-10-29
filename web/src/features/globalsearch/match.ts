/** 통합 검색 "내 제안서" 묶음 — 제목 일치·현재 단계 경로. 순수 함수. */
import type { RunState } from "@/api/types";

const norm = (s: string) => s.toLowerCase().replace(/\s+/g, "");

/** 제목에 검색어(공백 무시·대소문자 무시)가 들어간 제안서, 최근 수정 순 상위 n건. 검색어가 비면 최근 n건. */
export function matchProposals(runs: readonly RunState[], q: string, n = 5): RunState[] {
  const key = norm(q);
  const sorted = [...runs].sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""));
  const hits = key ? sorted.filter((r) => norm(r.title ?? "").includes(key)) : sorted;
  return hits.slice(0, n);
}

/** 그 제안서의 현재 단계 화면 (/runs/:id 아래 경로). 생성·검토 중이면 진행 화면. */
export function proposalPath(run: Pick<RunState, "run_id" | "status" | "legacy">): string {
  const base = `/runs/${run.run_id}`;
  if (run.legacy) return base;
  switch (run.status) {
    case "drafted":
      return `${base}/draft`;
    case "editing":
      return `${base}/edit`;
    case "final_reviewing":
    case "final_reviewed":
      return `${base}/final-review`;
    case "finalized":
      return `${base}/finalize`;
    default:
      return base;
  }
}
