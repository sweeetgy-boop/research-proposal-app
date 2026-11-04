/** 옛 화면 상태(출처 기록 전 sessionStorage) 읽기 — 출처를 AI 기본 선택으로 추정한다 (ADR 0056).
 *  모듈을 새로 읽어야 해서 따로 둔다. */
import type { PrecheckAlert, SimilarChoice } from "@/api/types";

const AI_ALERTS = [
  { doc_id: "alio:same", title: "같은 과제", tier: "own", similarity: 0.9, blocking: true, judgment: "same", judged_by: "argon" },
  { doc_id: "own:diff", title: "다른 과제", tier: "own", similarity: 0.8, blocking: false, judgment: "different", judged_by: "argon" },
] as unknown as PrecheckAlert[];
const DEFAULTS: SimilarChoice[] = [
  { doc_id: "alio:same", choice: "similar" },
  { doc_id: "own:diff", choice: "unrelated" },
];

afterEach(() => sessionStorage.clear());

describe("선택 출처 — 옛 화면 상태", () => {
  it("옛 화면 상태(sessionStorage)를 읽으면 출처를 기본 선택으로 추정한다", async () => {
    const pre = { notice: "", blocking: true, alerts: AI_ALERTS, default_choices: DEFAULTS };
    sessionStorage.setItem("rra-idea", JSON.stringify({ precheck: pre, similarChoices: { "alio:same": "similar", "own:diff": "similar" }, appliedChoices: { "own:diff": "similar" } }));
    vi.resetModules();
    const fresh = await import("@/features/idea/store");
    expect(fresh.getIdea().choiceSources).toEqual({ "alio:same": "ai_prefill", "own:diff": "user" });
    expect(fresh.getIdea().appliedChoiceSources).toEqual({ "own:diff": "user" });
    fresh.resetIdea();
  });
});
