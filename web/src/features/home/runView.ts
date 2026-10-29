/** 연구 작업실(홈)·내 제안서 표의 순수 규칙 — 상태 칩·진행률(6단계)·이어서 작성할 곳·상대 시각·
 *  탭·검색·정렬·건수. 화면은 이 함수만 부른다 (UI Research Studio, 레인 2). */
import type { RunState } from "@/api/types";
import { runStepTargets, stepLabel } from "@/lib/runSteps";
import { statusLabel } from "@/lib/sections";

export type ChipStatus = "writing" | "reviewing" | "done";

const REVIEWING = new Set(["draft_reviewing", "final_reviewing", "final_reviewed"]);
/** 작성 중 칩이지만 상태 이름을 그대로 보여 줄 상태 (멈춤·실패) */
const STOPPED = new Set(["interrupted", "failed", "invalid"]);

export const isFinished = (r: Pick<RunState, "status">): boolean => r.status === "finalized";

export function chipStatus(r: Pick<RunState, "status">): ChipStatus {
  if (isFinished(r)) return "done";
  if (REVIEWING.has(r.status)) return "reviewing";
  return "writing";
}

/** 칩 글자 — 기본은 칩 이름(작성 중·검토 중·마무리 완료), 멈춤·실패는 상태 이름 */
export function chipLabel(r: Pick<RunState, "status">): string | null {
  return STOPPED.has(r.status) ? statusLabel(r.status) : null;
}

/** 6단계 중 끝난 단계 수. ①·② 는 제안서가 생기기 전에 끝난다. */
export function completedSteps(r: Pick<RunState, "status">): number {
  switch (r.status) {
    case "drafted":
    case "editing":
      return 3;
    case "final_reviewing":
      return 4;
    case "final_reviewed":
      return 5;
    case "finalized":
      return 6;
    default:
      return 2; // 대기·생성·1차 검토·멈춤 — ③ 초안 생성 중
  }
}

/** 지금 단계 번호 (1~6) */
export const currentStep = (r: Pick<RunState, "status">): number => Math.min(completedSteps(r) + 1, 6);

export const progressPercent = (r: Pick<RunState, "status">): number => Math.round((completedSteps(r) / 6) * 100);

/** 진행 한 줄 설명 — "6단계 중 3단계 완료 · 다음: 직접 수정" */
export function progressText(r: Pick<RunState, "status">): string {
  const done = completedSteps(r);
  if (done >= 6) return "6단계 모두 완료";
  return `6단계 중 ${done}단계 완료 · 지금: ${stepLabel(currentStep(r))}`;
}

/** 이어서 작성할 주소 — 지금 단계 화면, 아직 못 여는 단계면 진행 화면 */
export function continuePath(r: RunState): string {
  const n = currentStep(r);
  const t = runStepTargets(r).find((x) => x.n === n);
  const sub = t?.to ?? "";
  return sub ? `/runs/${r.run_id}/${sub}` : `/runs/${r.run_id}`;
}

const time = (iso: string): number => {
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? 0 : t;
};

/** 가장 최근에 고친 작성 중 제안서 (없으면 null) */
export function latestInProgress(runs: RunState[]): RunState | null {
  let best: RunState | null = null;
  for (const r of runs) {
    if (isFinished(r) || r.legacy) continue;
    if (!best || time(r.updated_at) > time(best.updated_at)) best = r;
  }
  return best;
}

/** "방금 수정"·"5분 전 수정"·"3시간 전 수정"·"2일 전 수정" (30일 넘으면 날짜) */
export function relativeEdited(iso: string, now: Date = new Date()): string {
  const t = time(iso);
  if (!t) return "수정 시각 미상";
  const sec = Math.max(0, Math.floor((now.getTime() - t) / 1000));
  if (sec < 60) return "방금 수정";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}분 전 수정`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}시간 전 수정`;
  const day = Math.floor(hr / 24);
  if (day <= 30) return `${day}일 전 수정`;
  return `${new Date(t).toLocaleDateString("ko-KR")} 수정`;
}

export type RunTab = "all" | "writing" | "done";
export type RunSort = "recent" | "title" | "progress";

export const RUN_SORTS: { id: RunSort; label: string }[] = [
  { id: "recent", label: "최근 수정순" },
  { id: "title", label: "제목순" },
  { id: "progress", label: "진행률순" },
];

export const displayTitle = (r: Pick<RunState, "title">): string => r.title?.trim() || "제목 미정";

export interface RunCounts {
  all: number;
  writing: number;
  done: number;
}

export function runCounts(runs: RunState[]): RunCounts {
  const done = runs.filter(isFinished).length;
  return { all: runs.length, writing: runs.length - done, done };
}

/** 탭 → 검색(제목, 대소문자·공백 무시) → 정렬 */
export function visibleRuns(runs: RunState[], tab: RunTab, query: string, sort: RunSort): RunState[] {
  const q = query.trim().toLowerCase().replace(/\s+/g, "");
  const rows = runs.filter((r) => {
    if (tab === "writing" && isFinished(r)) return false;
    if (tab === "done" && !isFinished(r)) return false;
    if (!q) return true;
    return displayTitle(r).toLowerCase().replace(/\s+/g, "").includes(q);
  });
  const byRecent = (a: RunState, b: RunState) => time(b.updated_at) - time(a.updated_at);
  const sorted = [...rows];
  if (sort === "recent") sorted.sort(byRecent);
  else if (sort === "title") sorted.sort((a, b) => displayTitle(a).localeCompare(displayTitle(b), "ko") || byRecent(a, b));
  else sorted.sort((a, b) => completedSteps(b) - completedSteps(a) || byRecent(a, b));
  return sorted;
}
