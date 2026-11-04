/** ② [선택 적용] 선택 기록 (ADR 0056 2026-11-04 후속) — 누를 때마다 POST /v1/precheck/choices?apply=true 한 번,
 *  본문은 적용한 선택 + 출처. 화면에 들어오거나 행을 고르기만 해서는 보내지 않는다. 기록 실패는 화면을 막지 않는다. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockFetch, problem, renderWithProviders } from "@/test/utils";
import { clearSession } from "@/auth/session";
import { getIdea, resetIdea, updateIdea } from "@/features/idea/store";
import { emptyRequest } from "@/lib/validation";
import Precheck from "@/routes/Precheck";
import type { PrecheckAlert, PrecheckFlowOut, PrecheckOut, SimilarChoice } from "@/api/types";

afterEach(() => {
  vi.unstubAllGlobals();
  clearSession();
  resetIdea();
});

const alert = (over: Partial<PrecheckAlert>): PrecheckAlert => ({
  doc_id: "own:1",
  title: "궤도 상태 자동 감지 연구",
  tier: "own",
  similarity: 0.861,
  blocking: false,
  basis: "summary",
  keywords: ["궤도"],
  status: null,
  own_detail: "institute",
  tier_label: "사내(철도연구원)",
  rerank_score: 0.97,
  relevance: "high",
  relevance_label: "높음",
  source_label: "사내 과제 현황",
  judgment: null,
  judged_by: null,
  merged_ids: [],
  ...over,
});

const ALERTS = [
  alert({ doc_id: "alio:same", title: "같은 과제", blocking: true, judgment: "same", judgment_label: "같다", judged_by: "argon" }),
  alert({ doc_id: "own:part", title: "일부 겹치는 과제", judgment: "partial", judgment_label: "일부 겹침", judged_by: "argon" }),
  alert({ doc_id: "own:diff", title: "다른 과제", judgment: "different", judgment_label: "다르다", judged_by: "argon" }),
];
const DEFAULTS: SimilarChoice[] = [
  { doc_id: "alio:same", choice: "similar" },
  { doc_id: "own:part", choice: "similar" },
  { doc_id: "own:diff", choice: "unrelated" },
];
const JUDGED = { status: "ai" as const, judged_by: "argon", judged_by_label: "Argon", message: "판정", retry_available: false, candidates: 3, provider: "gemini", model: "argon", calls: 1 };
const COMPARISON = {
  notice: "",
  comparison: {
    aspects: [{ key: "objective", label: "연구목표" }],
    proposal: { doc_id: null, title: "가제", tier: null, similarity: null, blocking: false, basis: null, title_only: false, cells: { objective: "목표" } },
    projects: [],
    empty_reason: "유사한 과제를 고르면 비교표가 만들어집니다",
  },
};
const CARDS = {
  id: "rec-apply",
  skipped_reason: null,
  no_recommendation_reason: null,
  provider: "gemini",
  model: "argon",
  fallback_local: false,
  transfer: { public_doc_ids: [], internal_doc_ids: [], excluded_doc_ids: [], calls: 1 },
  recommendations: [],
  discarded: [],
};
const request = { ...emptyRequest(), current_state: "a", root_cause: "b", limitation: "c", goal: "목표", title_hint: "가제", policy_basis: "국토부 계획" };

type Body = { similar_choices?: SimilarChoice[]; goal?: string };
const APPLY = "/v1/precheck/choices?apply=true";

function setup(applyResponse: unknown = { notice: "", alerts: ALERTS, blocking: false }) {
  const { calls } = mockFetch({
    "/v1/precheck/choices": applyResponse,
    "/v1/precheck/recommendations": { notice: "", alerts: ALERTS, blocking: true, recommendations: CARDS },
    "/v1/precheck/comparison": COMPARISON,
    "/v1/precheck/differentiate": { notice: "", alerts: ALERTS, blocking: true, differentiation: undefined },
  });
  const pre: PrecheckFlowOut = { notice: "", blocking: true, alerts: ALERTS, judgment: JUDGED, default_choices: DEFAULTS };
  updateIdea({ precheck: pre as unknown as PrecheckOut, request });
  // 미리 고른 AI 기본 선택 (ai_prefill) — 새 확인 결과를 넣은 뒤에 (결과를 넣으면 선택이 비워진다)
  updateIdea({
    similarChoices: { "alio:same": "similar", "own:part": "similar", "own:diff": "unrelated" },
    choiceSources: { "alio:same": "ai_prefill", "own:part": "ai_prefill", "own:diff": "ai_prefill" },
  });
  renderWithProviders(<Precheck />, { route: "/new/precheck" });
  const applyCalls = () => calls.filter((c) => c.url === APPLY);
  const group = (title: string) => within(screen.getByRole("group", { name: `${title} 선택` }));
  return { calls, applyCalls, group };
}

const sentOf = (body: Body) => Object.fromEntries((body.similar_choices ?? []).map((c) => [c.doc_id, `${c.choice}/${c.source}`]));

describe("② [선택 적용] 선택 기록 요청", () => {
  it("누를 때마다 apply 요청 한 번 — 적용한 선택 + 출처, 들어오거나 고르기만 해서는 보내지 않는다", async () => {
    const { calls, applyCalls, group } = setup();
    await waitFor(() => expect(calls.some((c) => c.url === "/v1/precheck/comparison")).toBe(true));
    // 차단 행을 [관련 없음] 으로 바꿈 → user
    await userEvent.click(group("같은 과제").getByRole("button", { name: "관련 없음" }));
    expect(applyCalls()).toHaveLength(0);

    await userEvent.click(screen.getByRole("button", { name: "선택 적용" }));
    await waitFor(() => expect(applyCalls()).toHaveLength(1));
    const body = JSON.parse(String(applyCalls()[0]!.init!.body)) as Body;
    expect(sentOf(body)).toEqual({ "alio:same": "unrelated/user", "own:part": "similar/ai_prefill", "own:diff": "unrelated/ai_prefill" });
    expect(body.goal).toBe("목표"); // 같은 아이디어 입력(서버는 해시만 남긴다)
    expect(applyCalls()[0]!.init!.method).toBe("POST");
    // 비교표·활용 제안은 따로 그대로 — apply 요청은 여전히 한 번
    await waitFor(() => expect(calls.filter((c) => c.url === "/v1/precheck/differentiate").length).toBeGreaterThan(0));
    expect(applyCalls()).toHaveLength(1);

    // 선택을 바꿔 다시 적용 — 요청 하나 더, 새 선택
    await userEvent.click(group("다른 과제").getByRole("button", { name: "유사함" }));
    await userEvent.click(screen.getByRole("button", { name: "선택 적용" }));
    await waitFor(() => expect(applyCalls()).toHaveLength(2));
    expect(sentOf(JSON.parse(String(applyCalls()[1]!.init!.body)) as Body)["own:diff"]).toBe("similar/user");
    expect(getIdea().appliedChoiceSources?.["own:diff"]).toBe("user");
  });

  it("기록 요청이 실패해도 적용은 그대로 — 오류 문구를 보이지 않는다", async () => {
    const { applyCalls, group } = setup(problem(500, "기록 실패"));
    await userEvent.click(group("같은 과제").getByRole("button", { name: "관련 없음" }));
    await userEvent.click(screen.getByRole("button", { name: "선택 적용" }));
    await waitFor(() => expect(applyCalls()).toHaveLength(1));
    expect(getIdea().appliedChoices).toEqual({ "alio:same": "unrelated", "own:part": "similar", "own:diff": "unrelated" });
    expect(screen.queryByText("기록 실패")).not.toBeInTheDocument();
  });
});
