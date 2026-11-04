/** ② 선택 출처 (ADR 0056) — 행마다 미리 고른 AI 기본 선택(ai_prefill)인지 제안자가 바꾼 값(user)인지 기록하고,
 *  similar_choices 를 싣는 모든 요청에 source 를 함께 보낸다. 출처는 선택 기록용 — 화면 규칙(차단·건수)은 그대로. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockFetch, renderWithProviders } from "@/test/utils";
import { clearSession } from "@/auth/session";
import { getIdea, resetIdea, updateIdea } from "@/features/idea/store";
import { emptyRequest } from "@/lib/validation";
import Precheck from "@/routes/Precheck";
import Clarify from "@/routes/Clarify";
import type { PrecheckAlert, PrecheckFlowOut, PrecheckOut, SimilarChoice } from "@/api/types";
import { choiceCounts, choiceList, chooseRow, effectiveBlocking, inferSources, withDefaults } from "./model";

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

const RULE_ALERTS = [
  alert({ doc_id: "alio:same", title: "같은 과제", blocking: true, rule_blocking: true }),
  alert({ doc_id: "own:part", title: "일부 겹치는 과제" }),
  alert({ doc_id: "own:diff", title: "다른 과제" }),
  alert({ doc_id: "own:rule", title: "규칙 판정 과제" }),
];
const AI_ALERTS = [
  alert({ doc_id: "alio:same", title: "같은 과제", blocking: true, judgment: "same", judgment_label: "같다", judged_by: "argon" }),
  alert({ doc_id: "own:part", title: "일부 겹치는 과제", judgment: "partial", judgment_label: "일부 겹침", judged_by: "argon" }),
  alert({ doc_id: "own:diff", title: "다른 과제", judgment: "different", judgment_label: "다르다", judged_by: "argon" }),
  alert({ doc_id: "own:rule", title: "규칙 판정 과제", judged_by: "rule" }), // AI 판정 없음 — 기본 선택 없음
];
const DEFAULTS: SimilarChoice[] = [
  { doc_id: "alio:same", choice: "similar" },
  { doc_id: "own:part", choice: "similar" },
  { doc_id: "own:diff", choice: "unrelated" },
];
const JUDGED = { status: "ai" as const, judged_by: "argon", judged_by_label: "Argon", message: "판정", retry_available: false, candidates: 4, provider: "gemini", model: "argon", calls: 1 };
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
  id: "rec-src",
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

type Body = { similar_choices?: SimilarChoice[] };
const sentOf = (body: Body | undefined) => Object.fromEntries((body?.similar_choices ?? []).map((c) => [c.doc_id, `${c.choice}/${c.source}`]));

describe("선택 출처 규칙 (ADR 0056)", () => {
  it("미리 고른 값은 ai_prefill — 제안자가 이미 고른 값의 출처는 바꾸지 않는다", () => {
    const out = withDefaults({ "own:diff": "similar" }, DEFAULTS, AI_ALERTS, { "own:diff": "user" });
    expect(out.map).toEqual({ "own:diff": "similar", "alio:same": "similar", "own:part": "similar" });
    expect(out.sources).toEqual({ "own:diff": "user", "alio:same": "ai_prefill", "own:part": "ai_prefill" });
  });

  it("다른 값을 누르면 user, 기본 선택과 같은 값·지움(기본 선택으로 돌아감)은 ai_prefill, 기본 선택 없는 행은 user", () => {
    const { map, sources } = withDefaults({}, DEFAULTS, AI_ALERTS);
    const row = (id: string) => AI_ALERTS.find((a) => a.doc_id === id);
    // 다르다 → [관련 없음] 미리 고름 → [유사함] 으로 바꿈 = user
    let s = chooseRow(map, sources, row("own:diff"), "own:diff", "similar", DEFAULTS);
    expect([s.map["own:diff"], s.sources["own:diff"]]).toEqual(["similar", "user"]);
    // 다시 기본 선택과 같은 [관련 없음] 을 누르면 ai_prefill
    s = chooseRow(s.map, s.sources, row("own:diff"), "own:diff", "unrelated", DEFAULTS);
    expect([s.map["own:diff"], s.sources["own:diff"]]).toEqual(["unrelated", "ai_prefill"]);
    // 바꿨다가 지우면 기본 선택으로 돌아가고 ai_prefill
    s = chooseRow(s.map, s.sources, row("own:part"), "own:part", "unrelated", DEFAULTS);
    expect(s.sources["own:part"]).toBe("user");
    s = chooseRow(s.map, s.sources, row("own:part"), "own:part", null, DEFAULTS);
    expect([s.map["own:part"], s.sources["own:part"]]).toEqual(["similar", "ai_prefill"]);
    // 기본 선택이 없는 행에서 고르면 user, 지우면 선택·출처 모두 없음
    s = chooseRow(s.map, s.sources, row("own:rule"), "own:rule", "similar", DEFAULTS);
    expect(s.sources["own:rule"]).toBe("user");
    s = chooseRow(s.map, s.sources, row("own:rule"), "own:rule", null, DEFAULTS);
    expect("own:rule" in s.map || "own:rule" in s.sources).toBe(false);
  });

  it("묶음 행 — 구성원 doc_id 에 남은 선택과 출처를 함께 지운다", () => {
    const lead = alert({ doc_id: "own:lead", merged_ids: ["own:member"], judgment: "partial", judged_by: "argon" });
    const s = chooseRow({ "own:member": "unrelated" }, { "own:member": "user" }, lead, "own:lead", "unrelated", [{ doc_id: "own:lead", choice: "similar" }]);
    expect(s.map).toEqual({ "own:lead": "unrelated" });
    expect(s.sources).toEqual({ "own:lead": "user" });
  });

  it("출처는 화면 규칙을 바꾸지 않는다 — 차단·건수는 값만 본다", () => {
    const { map, sources } = withDefaults({}, DEFAULTS, AI_ALERTS);
    const user = Object.fromEntries(Object.keys(map).map((k) => [k, "user" as const]));
    expect(choiceList(map, sources).map(({ doc_id, choice }) => ({ doc_id, choice }))).toEqual(choiceList(map, user).map(({ doc_id, choice }) => ({ doc_id, choice })));
    expect(effectiveBlocking(AI_ALERTS, map)).toBe(true);
    expect(choiceCounts(AI_ALERTS, map)).toEqual({ similar: 2, unrelated: 1 });
  });

  it("choiceList — 출처가 없는 키는 user (서버 기본값과 같다)", () => {
    expect(choiceList({ a: "similar", b: "unrelated" }, { a: "ai_prefill" })).toEqual([
      { doc_id: "a", choice: "similar", source: "ai_prefill" },
      { doc_id: "b", choice: "unrelated", source: "user" },
    ]);
  });

  it("출처 기록 전에 저장된 상태 — 기본 선택과 같은 값은 ai_prefill, 다르면 user", () => {
    expect(inferSources({ "alio:same": "similar", "own:diff": "similar" }, DEFAULTS)).toEqual({ "alio:same": "ai_prefill", "own:diff": "user" });
  });

  it("새 유사과제 확인 결과는 선택과 함께 출처도 비운다", () => {
    updateIdea({ similarChoices: { a: "similar" }, choiceSources: { a: "user" }, appliedChoices: { a: "similar" }, appliedChoiceSources: { a: "user" } });
    updateIdea({ precheck: { notice: "", blocking: false, alerts: [] } as unknown as PrecheckOut });
    expect(getIdea().choiceSources).toEqual({});
    expect(getIdea().appliedChoiceSources).toBeNull();
  });
});

describe("② 화면 — 출처가 요청 본문에 실린다", () => {
  it("미리 고름 → 바꿈·같은 값·지움 → [선택 적용] 요청·다시 열기·생성 요청까지 source", async () => {
    const bodies: Record<string, Body[]> = {};
    const keep = (path: string, out: unknown) => (init?: RequestInit) => {
      (bodies[path] ??= []).push(JSON.parse(String(init?.body)) as Body);
      return out;
    };
    mockFetch({
      "/v1/precheck/judgment": keep("judgment", { notice: "", alerts: AI_ALERTS, blocking: true, judgment: JUDGED, default_choices: DEFAULTS }),
      "/v1/precheck/recommendations": keep("recommendations", { notice: "", alerts: AI_ALERTS, blocking: true, recommendations: CARDS }),
      "/v1/precheck/comparison": keep("comparison", COMPARISON),
      "/v1/precheck/differentiate": keep("differentiate", { notice: "", alerts: AI_ALERTS, blocking: true, differentiation: undefined }),
    });
    const pre: PrecheckFlowOut = { notice: "", blocking: true, alerts: RULE_ALERTS, judgment: { ...JUDGED, status: "pending", message: "기다리는 중" } };
    updateIdea({ precheck: pre as unknown as PrecheckOut, request });
    const first = renderWithProviders(<Precheck />, { route: "/new/precheck" });

    // AI 판정이 오면 기본 선택을 미리 고른다 — 모두 ai_prefill
    await waitFor(() => expect(getIdea().similarChoices).toEqual({ "alio:same": "similar", "own:part": "similar", "own:diff": "unrelated" }));
    expect(getIdea().choiceSources).toEqual({ "alio:same": "ai_prefill", "own:part": "ai_prefill", "own:diff": "ai_prefill" });
    const group = (title: string) => within(screen.getByRole("group", { name: `${title} 선택` }));

    // 다른 값을 누르면 user
    await userEvent.click(group("다른 과제").getByRole("button", { name: "유사함" }));
    expect(getIdea().choiceSources["own:diff"]).toBe("user");
    // 미리 고른 값을 눌러 지우면 기본 선택으로 돌아가고 ai_prefill 그대로
    await userEvent.click(group("일부 겹치는 과제").getByRole("button", { name: "유사함" }));
    expect([getIdea().similarChoices["own:part"], getIdea().choiceSources["own:part"]]).toEqual(["similar", "ai_prefill"]);
    // 바꿨다가 기본 선택과 같은 값을 다시 누르면 ai_prefill, 다시 바꾸면 user (차단 행 → [관련 없음] 으로 차단 해제)
    await userEvent.click(group("같은 과제").getByRole("button", { name: "관련 없음" }));
    expect(getIdea().choiceSources["alio:same"]).toBe("user");
    await userEvent.click(group("같은 과제").getByRole("button", { name: "유사함" }));
    expect(getIdea().choiceSources["alio:same"]).toBe("ai_prefill");
    await userEvent.click(group("같은 과제").getByRole("button", { name: "관련 없음" }));
    expect(getIdea().choiceSources["alio:same"]).toBe("user");
    // 기본 선택이 없는 행(규칙 판정)에서 고르면 user
    await userEvent.click(group("규칙 판정 과제").getByRole("button", { name: "관련 없음" }));
    expect(getIdea().choiceSources["own:rule"]).toBe("user");

    const expected = { "alio:same": "unrelated/user", "own:part": "similar/ai_prefill", "own:diff": "similar/user", "own:rule": "unrelated/user" };
    await userEvent.click(screen.getByRole("button", { name: "선택 적용" }));
    await waitFor(() => expect(sentOf(bodies.comparison?.at(-1))).toEqual(expected));
    await waitFor(() => expect(sentOf(bodies.differentiate?.at(-1))).toEqual(expected));
    await waitFor(() => expect(sentOf(bodies.recommendations?.at(-1))).toEqual(expected));
    expect(getIdea().appliedChoiceSources).toEqual(getIdea().choiceSources);

    // ② 를 닫았다 다시 열어도 출처가 남는다 (sessionStorage)
    first.unmount();
    const saved = JSON.parse(sessionStorage.getItem("rra-idea") ?? "{}") as { choiceSources?: Record<string, string> };
    expect(saved.choiceSources).toEqual({ "alio:same": "user", "own:part": "ai_prefill", "own:diff": "user", "own:rule": "user" });
    const before = bodies.comparison?.length ?? 0;
    renderWithProviders(<Precheck />, { route: "/new/precheck" });
    await waitFor(() => expect((bodies.comparison?.length ?? 0) > before).toBe(true));
    expect(sentOf(bodies.comparison?.at(-1))).toEqual(expected);

    // [다음] → ③ 생성 요청(POST /v1/runs)의 similar_choices 에도 출처
    await userEvent.click(screen.getByRole("button", { name: /다음: 선행연구 브리핑/ }));
    expect(sentOf(getIdea().request as Body)).toEqual(expected);
  });

  it("생성 요청 본문 — similar_choices 에 source", async () => {
    updateIdea({
      precheck: { notice: "", blocking: false, alerts: [] } as unknown as PrecheckOut,
      request: {
        ...request,
        similar_choices: [
          { doc_id: "alio:same", choice: "unrelated", source: "user" },
          { doc_id: "own:part", choice: "similar", source: "ai_prefill" },
        ],
      },
    });
    const { calls } = mockFetch({
      "/v1/precheck/clarify": { questions: [], skip_allowed: true, status: "enough", status_label: "", reason: null, reason_label: null, source: "argon", policy_needed: false },
      "/v1/runs": { run_id: "20260101000000-0000000a", status: "queued" },
    });
    renderWithProviders(<Clarify />);
    await userEvent.click(await screen.findByRole("button", { name: "초안 생성 시작" }));
    await waitFor(() => expect(calls.some((c) => c.url === "/v1/runs")).toBe(true));
    const body = JSON.parse(String(calls.find((c) => c.url === "/v1/runs")!.init!.body)) as Body;
    expect(sentOf(body)).toEqual({ "alio:same": "unrelated/user", "own:part": "similar/ai_prefill" });
  });
});
