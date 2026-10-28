/** ② v3 (레인 A, ADR 0039) — 표 먼저·판정 칸 매핑·유사도 숨김·선택 요약 막대(적용/바뀜)·카드 근거 상위 3·대기/취소. */
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations, renderWithProviders } from "@/test/utils";
import { clearSession } from "@/auth/session";
import { getIdea, resetIdea, updateIdea } from "@/features/idea/store";
import { emptyRequest } from "@/lib/validation";
import Precheck from "@/routes/Precheck";
import type { PlanRecommendations, PrecheckAlert, PrecheckFlowOut, PrecheckOut } from "@/api/types";
import { SimilarRowsTable } from "./SimilarRowsTable";
import { PlanCards } from "./PlanCards";
import { SummaryBar } from "./SummaryBar";
import { levelOf, withDefaults } from "./model";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  clearSession();
  resetIdea();
});

const INTERNAL_ID = /\b(own|alio|ntis|scienceon|openalex|korail_web|g2b):[\w-]+/;

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
  alert({ doc_id: "own:part", title: "일부 겹치는 과제", relevance: "mid", relevance_label: "보통" }),
  alert({ doc_id: "own:diff", title: "다른 과제", relevance: "low", relevance_label: "낮음" }),
];
const AI_ALERTS = [
  alert({ doc_id: "alio:same", title: "같은 과제", blocking: true, judgment: "same", judgment_label: "같다", judgment_reason: "대상·방법이 같음", judged_by: "argon" }),
  alert({ doc_id: "own:part", title: "일부 겹치는 과제", judgment: "partial", judgment_label: "일부 겹침", judgment_reason: "대상만 같음", judged_by: "argon" }),
  alert({ doc_id: "own:diff", title: "다른 과제", judgment: "different", judgment_label: "다르다", judgment_reason: "대상이 다름", judged_by: "argon" }),
];
const JUDGED = { status: "ai" as const, judged_by: "argon", judged_by_label: "Argon", message: "Argon 이 판정했습니다 — '같다' 만 차단합니다.", retry_available: false, candidates: 3, provider: "gemini", model: "argon", calls: 1 };

const card = (index: number, over: Record<string, unknown> = {}) => ({
  index,
  title: `과제안 ${"가나다라마"[index]}`,
  summary: "요약",
  goal: "목표",
  method: "방법",
  scope: "범위",
  differentiation: "차이",
  reasons: [],
  build_on: "",
  risks: "",
  compared_with: ["own:part"],
  evidence: [],
  overlap_warning: [],
  refs: [],
  ...over,
});
const CARDS: PlanRecommendations = {
  id: "rec-v3",
  skipped_reason: null,
  no_recommendation_reason: null,
  provider: "gemini",
  model: "argon",
  fallback_local: false,
  transfer: { public_doc_ids: [], internal_doc_ids: [], excluded_doc_ids: [], calls: 1 },
  recommendations: [card(0), card(1)],
  discarded: [],
};
const COMPARISON = {
  notice: "",
  comparison: {
    aspects: [{ key: "objective", label: "연구목표" }],
    proposal: { doc_id: null, title: "가제", tier: null, similarity: null, blocking: false, basis: null, title_only: false, cells: { objective: "목표" } },
    projects: [],
    empty_reason: "유사한 과제를 고르면 비교표가 만들어집니다",
  },
};
type Route = unknown | ((init?: RequestInit) => unknown);
/** 응답을 늦출 수 있는 fetch 대역 — 함수가 Promise<Response> 를 돌려주면 그대로 기다린다 */
function mockFetch(routes: Record<string, Route>) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      calls.push({ url, init });
      const key = Object.keys(routes).find((k) => url === k || url.startsWith(k + "?"));
      if (!key) return new Response(JSON.stringify({ status: 404, detail: "없음" }), { status: 404, headers: { "content-type": "application/problem+json" } });
      const v = routes[key];
      const body = await (typeof v === "function" ? (v as (i?: RequestInit) => unknown)(init) : v);
      if (body instanceof Response) return body;
      return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
    }),
  );
  return { calls };
}

const request = { ...emptyRequest(), current_state: "a", root_cause: "b", limitation: "c", goal: "목표", title_hint: "가제" };

describe("② v3 규칙", () => {
  it("판정 칸: 같다→차단·일부 겹침→근접·다르다→관련 낮음, AI 전엔 규칙 기준", () => {
    expect(AI_ALERTS.map((a) => levelOf(a).label)).toEqual(["차단", "근접", "관련 낮음"]);
    expect(RULE_ALERTS.map((a) => [levelOf(a).label, levelOf(a).basis])).toEqual([
      ["차단", "rule"],
      ["근접", "rule"],
      ["근접", "rule"],
    ]);
  });

  it("기본 선택: 선택이 없는 행에만 '다르다' → [관련 없음]", () => {
    const { map, added } = withDefaults({ "own:diff": "similar" }, [{ doc_id: "own:diff", choice: "unrelated" }], AI_ALERTS);
    expect(map).toEqual({ "own:diff": "similar" }); // 제안자가 고른 값은 그대로
    expect(added).toBe(0);
    expect(withDefaults({}, [{ doc_id: "own:diff", choice: "unrelated" }], AI_ALERTS)).toEqual({ map: { "own:diff": "unrelated" }, added: 1 });
  });
});

describe("② v3 화면 조각", () => {
  it("표 — 판정 칸·관련도 말·규칙 기준 표시, 유사도 숫자·내부 번호 없음 (axe 0)", async () => {
    const { container, rerender } = renderWithProviders(<SimilarRowsTable alerts={RULE_ALERTS} choices={{}} onChoose={vi.fn()} judging />);
    expect(screen.getAllByText("규칙 기준").length).toBe(3);
    expect(screen.getAllByText("AI 판정 기다리는 중").length).toBe(3);
    rerender(<SimilarRowsTable alerts={AI_ALERTS} choices={{}} onChoose={vi.fn()} />);
    const levels = screen.getAllByTestId("level").map((c) => c.textContent);
    expect(levels).toEqual(["차단", "근접", "관련 낮음"]);
    expect(screen.getAllByTestId("relevance").map((c) => c.textContent)).toEqual(["높음", "높음", "높음"]);
    expect(container.textContent).not.toMatch(/유사도|0\.86/);
    expect(container.textContent).not.toMatch(INTERNAL_ID);
    expect(screen.getAllByText(/사내 과제 현황/).length).toBe(3);
    await expectNoA11yViolations(container);
  });

  it("선택 요약 막대 — 건수, 바뀌면 [선택 적용] 켜짐·안내, 적용 뒤 '선택 적용됨' (axe 0)", async () => {
    const onApply = vi.fn();
    const props = { onApply, onMore: vi.fn(), moreDisabled: false, morePending: false, moreElapsed: 0, onCancelMore: vi.fn(), applying: false };
    const { container, rerender } = renderWithProviders(<SummaryBar similar={2} unrelated={1} stale applied={false} {...props} />);
    expect(screen.getByText(/유사함/).textContent).toMatch(/유사함 2건 · 관련 없음 1건/);
    const apply = screen.getByRole("button", { name: "선택 적용" });
    expect(apply).toBeEnabled();
    expect(screen.getByText(/선택이 바뀌었습니다/)).toBeInTheDocument();
    await userEvent.click(apply);
    expect(onApply).toHaveBeenCalled();
    rerender(<SummaryBar similar={2} unrelated={1} stale={false} applied {...props} />);
    expect(screen.getByRole("button", { name: "선택 적용" })).toBeDisabled();
    expect(screen.getByText("선택 적용됨 · 비교표 갱신")).toBeInTheDocument();
    expect(screen.getByTestId("precheck-summary-bar").getAttribute("style")).toContain("var(--stepnav-h, 0px)");
    await expectNoA11yViolations(container);
  });

  it("카드 — 근거는 제목·자료원 상위 3건 + [더 보기], 겹침 경고는 제목·겹치는 점 (axe 0)", async () => {
    const refs = ["가", "나", "다", "라", "마"].map((x, i) => ({ doc_id: `own:${i}`, title: `근거 과제 ${x}`, source_label: "사내 과제 현황" }));
    const rec: PlanRecommendations = {
      ...CARDS,
      recommendations: [
        card(0, {
          refs,
          difference: "low",
          difference_label: "낮음",
          overlap_warning: ["own:0"],
          overlap_titles: ["기상 반영 수요 예측"],
          overlap_reason: "둘 다 기상 변수를 넣은 수요 예측 모형",
          overlap_by: "argon",
          overlap_by_label: "Argon 판정",
          regenerated: true,
        }),
      ],
    };
    const { container } = renderWithProviders(
      <PlanCards rec={rec} waiting={{ pending: false, elapsed: 0, cancelled: false, onCancel: vi.fn() }} chosenIndex={null} stale={false} onPick={vi.fn()} onKeepOriginal={vi.fn()} onWrite={vi.fn()} onRegenerate={vi.fn()} />,
    );
    const list = screen.getByTestId("card-refs");
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);
    await userEvent.click(screen.getByRole("button", { name: "더 보기 (2건)" }));
    expect(within(screen.getByTestId("card-refs")).getAllByRole("listitem")).toHaveLength(5);
    const warn = screen.getByTestId("overlap-warning");
    expect(warn).toHaveTextContent("「기상 반영 수요 예측」");
    expect(warn).toHaveTextContent("겹치는 점: 둘 다 기상 변수를 넣은 수요 예측 모형");
    expect(screen.getByText(/한 번 다시 만든 안/)).toBeInTheDocument();
    expect(screen.getByText("차별성 낮음")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(INTERNAL_ID);
    await expectNoA11yViolations(container);
  });
});

describe("② v3 화면 전체", () => {
  it("표 먼저 → AI 판정 대기(경과·취소) → 판정이 오면 칸·기본 선택 → [선택 적용] 으로 비교표 다시", async () => {
    let releaseJudge: (r: Response) => void = () => {};
    const comparisonBodies: unknown[] = [];
    const { calls } = mockFetch({
      "/v1/precheck/judgment": () =>
        new Promise<Response>((res) => {
          releaseJudge = res;
        }),
      "/v1/precheck/recommendations": { notice: "", alerts: AI_ALERTS, blocking: true, recommendations: CARDS },
      "/v1/precheck/comparison": (init?: RequestInit) => {
        comparisonBodies.push(JSON.parse(String(init?.body)));
        return COMPARISON;
      },
    });
    const pre: PrecheckFlowOut = {
      notice: "",
      blocking: true,
      alerts: RULE_ALERTS,
      judgment: { ...JUDGED, status: "pending", message: "AI 판정 기다리는 중" },
    };
    updateIdea({ precheck: pre as unknown as PrecheckOut, request });
    renderWithProviders(<Precheck />, { route: "/new/precheck" });
    // 표가 먼저 — 규칙 기준, AI 판정 대기 표시와 [취소]
    expect(screen.getAllByText("규칙 기준").length).toBeGreaterThan(0);
    expect(await screen.findByText(/AI 판정 — 응답 기다리는 중 · 경과 0초/)).toBeInTheDocument();
    expect(calls.some((c) => c.url.startsWith("/v1/precheck/recommendations"))).toBe(true); // 과제안도 바로 시작
    expect(await screen.findAllByTestId("plan-card")).toHaveLength(2);
    // 판정 도착
    await act(async () => {
      releaseJudge(
        new Response(JSON.stringify({ notice: "", alerts: AI_ALERTS, blocking: true, judgment: JUDGED, default_choices: [{ doc_id: "own:diff", choice: "unrelated" }] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    });
    await waitFor(() => expect(screen.getAllByTestId("level").map((c) => c.textContent)).toEqual(["차단", "근접", "관련 낮음"]));
    expect(getIdea().similarChoices).toEqual({ "own:diff": "unrelated" }); // 다르다만 미리 고름
    expect(screen.getByText(/'다르다' 로 본 1건은 \[관련 없음\]/)).toBeInTheDocument();
    // 선택 → 비교표는 아직 그대로(바뀜 안내) → [선택 적용]
    const before = comparisonBodies.length;
    await userEvent.click(within(screen.getByRole("group", { name: "일부 겹치는 과제 선택" })).getByRole("button", { name: "유사함" }));
    expect(comparisonBodies.length).toBe(before); // 클릭만으로는 다시 만들지 않는다
    expect(screen.getByText(/선택이 바뀌었습니다/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "선택 적용" }));
    expect(await screen.findByText("선택 적용됨 · 비교표 갱신")).toBeInTheDocument();
    await waitFor(() => expect(comparisonBodies.length).toBe(before + 1));
    const sent = comparisonBodies.at(-1) as { similar_choices: { doc_id: string; choice: string }[] };
    expect(sent.similar_choices).toContainEqual({ doc_id: "own:part", choice: "similar" });
  });

  it("AI 판정 [취소] — 표는 규칙 기준 그대로, [다시 시도] 가 남는다", async () => {
    mockFetch({
      "/v1/precheck/judgment": (init?: RequestInit) =>
        new Promise<Response>((_res, rej) => {
          init?.signal?.addEventListener("abort", () => rej(new DOMException("aborted", "AbortError")));
        }),
      "/v1/precheck/recommendations": { notice: "", alerts: RULE_ALERTS, blocking: true, recommendations: CARDS },
      "/v1/precheck/comparison": COMPARISON,
    });
    updateIdea({
      precheck: { notice: "", blocking: true, alerts: RULE_ALERTS, judgment: { ...JUDGED, status: "pending", message: "" }, recommendations: CARDS } as unknown as PrecheckOut,
      request,
    });
    renderWithProviders(<Precheck />, { route: "/new/precheck" });
    const notice = await screen.findByTestId("judgment-notice");
    await userEvent.click(within(notice).getByRole("button", { name: "취소" }));
    expect(await screen.findByText("AI 판정을 취소했습니다 — 규칙 기준")).toBeInTheDocument();
    expect(within(screen.getByTestId("judgment-notice")).getByRole("button", { name: "다시 시도" })).toBeInTheDocument();
    expect(screen.getAllByTestId("level").map((c) => c.textContent)).toEqual(["차단규칙 기준", "근접규칙 기준", "근접규칙 기준"]);
  });
});
