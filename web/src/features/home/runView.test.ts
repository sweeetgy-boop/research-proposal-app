import type { RunState } from "@/api/types";
import drafted from "@/test/fixtures/run_drafted.json";
import {
  chipLabel,
  chipStatus,
  completedSteps,
  continuePath,
  latestInProgress,
  progressPercent,
  relativeEdited,
  runCounts,
  visibleRuns,
} from "./runView";

const base = drafted as unknown as RunState;
const run = (id: string, status: string, updated: string, title: string | null = `과제 ${id}`): RunState => ({
  ...base,
  run_id: id,
  status: status as RunState["status"],
  updated_at: updated,
  title,
  flow: { ...base.flow, has_working: false },
});

describe("홈 표 규칙", () => {
  it("상태 → 칩·진행률(6단계 중 끝난 단계)", () => {
    expect(chipStatus({ status: "running" })).toBe("writing");
    expect(chipStatus({ status: "final_reviewing" })).toBe("reviewing");
    expect(chipStatus({ status: "finalized" })).toBe("done");
    expect(chipLabel({ status: "failed" })).toBe("실패");
    expect(chipLabel({ status: "drafted" })).toBeNull();
    expect(completedSteps({ status: "running" })).toBe(2);
    expect(progressPercent({ status: "drafted" })).toBe(50);
    expect(progressPercent({ status: "finalized" })).toBe(100);
  });

  it("이어서 작성 — 가장 최근 작성 중, 지금 단계 화면", () => {
    const runs = [
      run("a", "drafted", "2026-10-28T01:00:00Z"),
      run("b", "finalized", "2026-10-29T01:00:00Z"),
      run("c", "running", "2026-10-27T01:00:00Z"),
    ];
    const latest = latestInProgress(runs)!;
    expect(latest.run_id).toBe("a");
    expect(continuePath(latest)).toBe("/runs/a/edit");
    expect(continuePath(runs[2]!)).toBe("/runs/c");
    expect(latestInProgress([runs[1]!])).toBeNull();
  });

  it("탭·검색·정렬·건수", () => {
    const runs = [
      run("a", "drafted", "2026-10-28T01:00:00Z", "궤도 틀림 예측"),
      run("b", "finalized", "2026-10-29T01:00:00Z", "전차선 마모"),
      run("c", "final_reviewed", "2026-10-27T01:00:00Z", "가선 점검"),
    ];
    expect(runCounts(runs)).toEqual({ all: 3, writing: 2, done: 1 });
    expect(visibleRuns(runs, "all", "", "recent").map((r) => r.run_id)).toEqual(["b", "a", "c"]);
    expect(visibleRuns(runs, "writing", "", "recent").map((r) => r.run_id)).toEqual(["a", "c"]);
    expect(visibleRuns(runs, "done", "", "recent").map((r) => r.run_id)).toEqual(["b"]);
    expect(visibleRuns(runs, "all", "틀림 예측", "recent").map((r) => r.run_id)).toEqual(["a"]);
    expect(visibleRuns(runs, "all", "", "title").map((r) => r.run_id)).toEqual(["c", "a", "b"]);
    expect(visibleRuns(runs, "all", "", "progress").map((r) => r.run_id)).toEqual(["b", "c", "a"]);
  });

  it("상대 시각", () => {
    const now = new Date("2026-10-29T12:00:00Z");
    expect(relativeEdited("2026-10-29T11:59:30Z", now)).toBe("방금 수정");
    expect(relativeEdited("2026-10-29T11:00:00Z", now)).toBe("1시간 전 수정");
    expect(relativeEdited("2026-10-27T12:00:00Z", now)).toBe("2일 전 수정");
    expect(relativeEdited("x", now)).toBe("수정 시각 미상");
  });
});
