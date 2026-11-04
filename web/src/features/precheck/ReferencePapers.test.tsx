/** ② 관련 연구 → 참고 논문 (ADR 0053) — [차별화에 참고] 체크·5건 상한, 요청의 reference_ids, 비교표 '선행연구' 열,
 *  추천 0건 안내(hint=reference)와 두 단추, ③ 생성 요청. */
import * as React from "react";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations, mockFetch, renderWithProviders } from "@/test/utils";
import { clearSession } from "@/auth/session";
import { getIdea, resetIdea, updateIdea } from "@/features/idea/store";
import { RelatedResearchList } from "@/features/idea/RelatedResearchList";
import { setPolicyChoice } from "@/features/policy/store";
import { emptyRequest } from "@/lib/validation";
import Precheck from "@/routes/Precheck";
import Clarify from "@/routes/Clarify";
import type { ComparisonFlow, PlanRecommendations, PrecheckAlert, PrecheckFlowOut, PrecheckOut, RelatedResearch } from "@/api/types";
import { ComparisonView } from "./ComparisonView";
import { PlanCards } from "./PlanCards";
import { toggleReference } from "./model";

afterEach(() => {
  vi.unstubAllGlobals();
  clearSession();
  resetIdea();
});

const INTERNAL_ID = /\b(own|alio|ntis|scienceon|openalex|korail_web|g2b|kipris):[\w-]+/;

const paper = (i: number, over: Partial<RelatedResearch> = {}): RelatedResearch => ({
  doc_id: `scienceon:p${i}`,
  title: `도시 비둘기 연구 ${i} (가짜)`,
  source: "scienceon",
  source_label: "ScienceON 국내 논문·보고서",
  doc_type: "paper",
  year: 2025,
  similarity: 0.8,
  url: null,
  ...over,
});
const RELATED: RelatedResearch[] = [paper(1, { live: true, title: "<b>실시간</b> 비둘기 논문 (가짜)" }), paper(2)];

const ALERT: PrecheckAlert = {
  doc_id: "own:1",
  title: "역사 조류 퇴치 과제",
  tier: "own",
  similarity: 0.82,
  blocking: false,
  basis: "summary",
  keywords: ["조류"],
  status: null,
  own_detail: "institute",
  tier_label: "사내(철도연구원)",
  relevance: "mid",
  relevance_label: "보통",
  source_label: "사내 과제 현황",
  judgment: "different",
  judgment_label: "다르다",
  judged_by: "argon",
  merged_ids: [],
};
const JUDGED = { status: "ai" as const, judged_by: "argon", judged_by_label: "Argon", message: "Argon 이 판정했습니다.", retry_available: false, candidates: 1, provider: "gemini", model: "argon", calls: 1 };

const recs = (over: Partial<PlanRecommendations> = {}): PlanRecommendations => ({
  id: "rec-ref",
  skipped_reason: null,
  no_recommendation_reason: null,
  provider: "gemini",
  model: "argon",
  fallback_local: false,
  transfer: { public_doc_ids: [], internal_doc_ids: [], excluded_doc_ids: [], calls: 1 },
  recommendations: [
    {
      index: 0,
      title: "비둘기 침입 감지 과제안",
      summary: "요약",
      goal: "목표",
      method: "방법",
      scope: "범위",
      differentiation: "차이",
      reasons: [],
      build_on: "",
      risks: "",
      compared_with: [],
      evidence: [],
      overlap_warning: [],
      refs: [],
    },
  ],
  discarded: [],
  ...over,
});
const ZERO = recs({
  recommendations: [],
  no_recommendation_reason: "기존 과제들과 차별성을 갖는 과제를 추천할 수 없습니다",
  hint: "reference",
  retry_used: true,
});

const COMPARISON: ComparisonFlow = {
  aspects: [{ key: "objective", label: "연구목표" }],
  proposal: { doc_id: null, title: "가제", tier: null, similarity: null, blocking: false, basis: null, title_only: false, cells: { objective: "목표" } },
  projects: [],
  empty_reason: "유사한 과제를 고르면 비교표가 만들어집니다",
} as unknown as ComparisonFlow;

const request = { ...emptyRequest(), current_state: "a", root_cause: "b", limitation: "c", goal: "목표", title_hint: "가제" };

function precheckWith(recommendations: PlanRecommendations): PrecheckFlowOut {
  return { notice: "", blocking: false, alerts: [ALERT], judgment: JUDGED, recommendations, related_research: RELATED } as unknown as PrecheckFlowOut;
}

const bodyOf = (calls: { url: string; init?: RequestInit }[], url: string) =>
  calls.filter((c) => c.url === url).map((c) => JSON.parse(String(c.init?.body)) as Record<string, unknown>);

/** 상태를 들고 있는 감싸개 — 실제 화면처럼 체크가 목록에 반영된다 */
function Harness({ items }: { items: RelatedResearch[] }) {
  const [ids, setIds] = React.useState<string[]>([]);
  return <RelatedResearchList items={items} selected={ids} onToggle={(id, on) => setIds((cur) => toggleReference(cur, id, on))} />;
}

describe("② 관련 연구 [차별화에 참고]", () => {
  it("행마다 체크(기본 해제, 실시간 항목 포함) — 접근 이름에 제목, 내부 번호 없음 (axe 0)", async () => {
    const { container } = renderWithProviders(<Harness items={RELATED} />);
    const boxes = screen.getAllByRole("checkbox");
    expect(boxes).toHaveLength(2);
    for (const b of boxes) expect(b).not.toBeChecked();
    // 비신뢰 제목은 텍스트 그대로(태그 해석 없음)
    const live = screen.getByRole("checkbox", { name: "차별화에 참고 — <b>실시간</b> 비둘기 논문 (가짜)" });
    expect(container.querySelector("b")).toBeNull();
    await userEvent.click(live);
    expect(live).toBeChecked();
    expect(screen.getByTestId("reference-limit-note")).toHaveTextContent("참고로 고른 자료 1건 (최대 5건)");
    await userEvent.click(live);
    expect(live).not.toBeChecked();
    expect(container.textContent).not.toMatch(INTERNAL_ID);
    await expectNoA11yViolations(container);
  });

  it("5건까지 — 다섯 건이면 나머지 체크는 막히고 안내 (axe 0)", async () => {
    const items = [1, 2, 3, 4, 5, 6].map((i) => paper(i));
    const { container } = renderWithProviders(<Harness items={items} />);
    const boxes = screen.getAllByTestId("reference-checkbox");
    for (const b of boxes.slice(0, 5)) await userEvent.click(b);
    expect(boxes[5]).toBeDisabled();
    expect(screen.getByTestId("reference-limit-note")).toHaveTextContent("참고 논문은 5건까지 고를 수 있습니다");
    expect(screen.getByTestId("reference-limit-note")).toHaveAttribute("aria-live", "polite");
    await userEvent.click(boxes[0]!); // 하나를 풀면 다시 고를 수 있다
    expect(boxes[5]).toBeEnabled();
    expect(toggleReference(["a", "b", "c", "d", "e"], "f", true)).toEqual(["a", "b", "c", "d", "e"]);
    await expectNoA11yViolations(container);
  });

  it("읽기 전용(onToggle 없음)이면 체크 없이 고른 행에 배지만", () => {
    renderWithProviders(<RelatedResearchList items={RELATED} selected={["scienceon:p2"]} />);
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.getAllByText("차별화에 참고")).toHaveLength(1);
  });
});

describe("② 화면 — reference_ids 가 요청에 실린다", () => {
  it("체크 → '선택이 바뀌었습니다' → [선택 적용] 의 비교표·활용 제안·과제안 요청에 reference_ids, ② 다시 열어도 남는다", async () => {
    const { calls } = mockFetch({
      "/v1/precheck/comparison": { notice: "", comparison: COMPARISON },
      "/v1/precheck/differentiate": { notice: "", alerts: [ALERT], blocking: false, differentiation: null },
      "/v1/precheck/recommendations": { notice: "", alerts: [ALERT], blocking: false, recommendations: recs() },
    });
    updateIdea({ precheck: precheckWith(recs()) as unknown as PrecheckOut, request });
    const { unmount } = renderWithProviders(<Precheck />, { route: "/new/precheck" });
    await waitFor(() => expect(bodyOf(calls, "/v1/precheck/comparison").length).toBeGreaterThan(0));
    for (const b of bodyOf(calls, "/v1/precheck/comparison")) expect(b.reference_ids).toEqual([]);

    await userEvent.click(screen.getByRole("checkbox", { name: /차별화에 참고 — .*실시간.* 비둘기 논문/ }));
    const cmpBefore = bodyOf(calls, "/v1/precheck/comparison").length;
    expect(getIdea().referenceIds).toEqual(["scienceon:p1"]);
    expect(within(screen.getByTestId("precheck-summary-bar")).getByText(/^선택이 바뀌었습니다/)).toBeInTheDocument();
    expect(screen.getByText(/참고 논문 선택이 바뀌었습니다/)).toBeInTheDocument();
    expect(screen.getByTestId("precheck-summary-bar")).toHaveTextContent("참고 논문 1건");

    expect(bodyOf(calls, "/v1/precheck/comparison")).toHaveLength(cmpBefore); // 체크만으로는 다시 만들지 않는다
    await userEvent.click(screen.getByRole("button", { name: "선택 적용" }));
    await waitFor(() => expect(bodyOf(calls, "/v1/precheck/comparison")).toHaveLength(cmpBefore + 1));
    expect(bodyOf(calls, "/v1/precheck/comparison").at(-1)!.reference_ids).toEqual(["scienceon:p1"]);
    // 유사함 0건이어도 참고 논문이 있으면 활용 제안을 받는다
    await waitFor(() => expect(bodyOf(calls, "/v1/precheck/differentiate")).toHaveLength(1));
    expect(bodyOf(calls, "/v1/precheck/differentiate")[0]!.reference_ids).toEqual(["scienceon:p1"]);
    await waitFor(() => expect(bodyOf(calls, "/v1/precheck/recommendations")).toHaveLength(1));
    expect(bodyOf(calls, "/v1/precheck/recommendations")[0]!.reference_ids).toEqual(["scienceon:p1"]);
    expect(await screen.findByText("선택 적용됨 · 비교표 갱신")).toBeInTheDocument();
    expect(getIdea().appliedReferenceIds).toEqual(["scienceon:p1"]);
    expect(JSON.parse(sessionStorage.getItem("rra-idea") ?? "{}").referenceIds).toEqual(["scienceon:p1"]);

    // [차별화 과제안 더 만들기] 도 지금 고른 참고 논문으로
    await userEvent.click(screen.getByRole("button", { name: "차별화 과제안 더 만들기" }));
    await waitFor(() => expect(calls.some((c) => c.url === "/v1/precheck/recommendations/more")).toBe(true));
    const more = bodyOf(calls, "/v1/precheck/recommendations/more")[0] as { request: { reference_ids: string[] } };
    expect(more.request.reference_ids).toEqual(["scienceon:p1"]);

    // ③ 에서 ② 로 돌아온 것처럼 다시 그려도 체크가 남는다
    unmount();
    renderWithProviders(<Precheck />, { route: "/new/precheck" });
    expect(screen.getByRole("checkbox", { name: /실시간.* 비둘기 논문/ })).toBeChecked();
    expect(within(screen.getByTestId("precheck-summary-bar")).queryByText(/^선택이 바뀌었습니다/)).toBeNull();
  });

  it("추천 0건 + hint=reference — 안내·[관련 연구로 이동]·고른 뒤 [과제안 다시 만들기] 요청에 reference_ids", async () => {
    const { calls } = mockFetch({
      "/v1/precheck/comparison": { notice: "", comparison: COMPARISON },
      "/v1/precheck/recommendations": { notice: "", alerts: [ALERT], blocking: false, recommendations: recs() },
    });
    updateIdea({ precheck: precheckWith(ZERO) as unknown as PrecheckOut, request });
    const { container } = renderWithProviders(<Precheck />, { route: "/new/precheck" });
    expect(screen.getByText("기존 과제들과 차별성을 갖는 과제를 추천할 수 없습니다")).toBeInTheDocument();
    const hint = screen.getByTestId("plan-reference-hint");
    expect(hint).toHaveTextContent("관련 연구에서 참고 논문을 골라 [과제안 다시 만들기]");
    expect(screen.getByTestId("plan-retry-note")).toBeInTheDocument();
    const actions = screen.getByTestId("plan-empty-actions");
    const regen = within(actions).getByRole("button", { name: "과제안 다시 만들기" });
    expect(regen).toBeDisabled(); // 아직 고른 논문이 없다
    await userEvent.click(within(hint).getByRole("button", { name: "관련 연구로 이동" }));
    expect(screen.getByRole("heading", { name: /관련 연구 2건/ })).toHaveFocus();
    await userEvent.click(screen.getAllByTestId("reference-checkbox")[1]!);
    expect(regen).toBeEnabled();
    await expectNoA11yViolations(container);
    await userEvent.click(regen);
    await waitFor(() => expect(bodyOf(calls, "/v1/precheck/recommendations")).toHaveLength(1));
    expect(bodyOf(calls, "/v1/precheck/recommendations")[0]!.reference_ids).toEqual(["scienceon:p2"]);
    expect(await screen.findAllByTestId("plan-card")).toHaveLength(1);
    expect(container.textContent).not.toMatch(INTERNAL_ID);
  });

  it("③ 생성 요청에도 reference_ids", async () => {
    resetIdea();
    setPolicyChoice(null);
    updateIdea({
      precheck: precheckWith(recs()) as unknown as PrecheckOut,
      request: { ...request, policy_basis: "국토부 철도안전 종합계획" },
      referenceIds: ["scienceon:p2"],
    });
    const { calls } = mockFetch({
      "/v1/precheck/clarify": { questions: [], skip_allowed: true, status: "enough", status_label: "", reason: null, reason_label: null, source: "argon", policy_needed: false },
      "/v1/runs": { run_id: "20260101000000-00000009", status: "queued" },
    });
    renderWithProviders(<Clarify />);
    await userEvent.click(await screen.findByRole("button", { name: "초안 생성 시작" }));
    await waitFor(() => expect(calls.some((c) => c.url === "/v1/runs")).toBe(true));
    expect(bodyOf(calls, "/v1/runs")[0]!.reference_ids).toEqual(["scienceon:p2"]);
  });
});

describe("비교표·과제안 조각", () => {
  it("kind=reference 열은 구분 '선행연구', kind 가 없으면 유사과제 (axe 0)", async () => {
    const col = (over: Record<string, unknown>) => ({ tier: "own", similarity: null, blocking: false, basis: null, title_only: false, cells: { objective: "목표" }, ...over });
    const data = {
      ...COMPARISON,
      empty_reason: null,
      projects: [col({ doc_id: "own:1", title: "역사 조류 퇴치 과제" }), col({ doc_id: "scienceon:p1", title: "도시 비둘기 논문", tier: "scienceon", kind: "reference" })],
    } as unknown as ComparisonFlow;
    const { container } = renderWithProviders(<ComparisonView data={data} />);
    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(within(rows[1]!).getByTestId("comparison-kind")).toHaveTextContent("유사과제");
    expect(within(rows[2]!).getByTestId("comparison-kind")).toHaveTextContent("선행연구");
    expect(screen.getByText(/참고로 고른 선행연구 1건/)).toBeInTheDocument();
    expect(container.textContent).not.toMatch(INTERNAL_ID);
    await expectNoA11yViolations(container);

    // 유사과제만이면 예전 모양 그대로 (구분 배지 없음)
    const { container: c2 } = renderWithProviders(<ComparisonView data={{ ...data, projects: [data.projects[0]!] }} />);
    expect(within(c2 as HTMLElement).queryByTestId("comparison-kind")).toBeNull();
  });

  it("참고 논문 열에 '검색 관련도 높음·중간·낮음' — 숫자는 보이지 않고, 관련도가 없으면 표시 없음 (axe 0)", async () => {
    const col = (over: Record<string, unknown>) => ({ tier: "scienceon", similarity: 0.9012, blocking: false, basis: null, title_only: false, cells: { objective: "목표" }, kind: "reference", ...over });
    const data = {
      ...COMPARISON,
      empty_reason: null,
      projects: [
        { tier: "own", similarity: 0.88, blocking: false, basis: null, title_only: false, cells: { objective: "목표" }, doc_id: "own:1", title: "역사 조류 퇴치 과제" },
        col({ doc_id: "scienceon:p1", title: "높은 논문", relevance: "high" }),
        col({ doc_id: "scienceon:p2", title: "중간 논문", relevance: "mid" }),
        col({ doc_id: "scienceon:p3", title: "낮은 논문", relevance: "low" }),
        col({ doc_id: "scienceon:p4", title: "모르는 논문", relevance: null, similarity: null }),
      ],
    } as unknown as ComparisonFlow;
    const { container } = renderWithProviders(<ComparisonView data={data} />);
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(within(rows[1]!).queryByTestId("reference-relevance")).toBeNull(); // 유사과제 열에는 없다
    expect(within(rows[2]!).getByTestId("reference-relevance")).toHaveTextContent("검색 관련도 높음");
    expect(within(rows[3]!).getByTestId("reference-relevance")).toHaveTextContent("검색 관련도 중간");
    expect(within(rows[4]!).getByTestId("reference-relevance")).toHaveTextContent("검색 관련도 낮음");
    expect(within(rows[5]!).queryByTestId("reference-relevance")).toBeNull();
    // 좁은 화면 카드에도 같은 말
    const cards = screen.getByRole("list", { name: /과제별 카드/ });
    expect(within(cards).getAllByText(/^검색 관련도 (높음|중간|낮음)$/)).toHaveLength(3);
    expect(container.textContent).not.toMatch(/0\.9012|0\.88\b/); // 숫자 없음 (ADR 0039)
    expect(container.textContent).not.toMatch(INTERNAL_ID);
    await expectNoA11yViolations(container);
  });

  it("추천 0건 hint=reference — 두 단추가 각각 다시 만들기·원래 아이디어로 진행 (axe 0)", async () => {
    const onRegenerate = vi.fn();
    const onKeepOriginal = vi.fn();
    const { container } = renderWithProviders(
      <PlanCards
        rec={ZERO}
        waiting={{ pending: false, elapsed: 0, cancelled: false, onCancel: vi.fn() }}
        chosenIndex={null}
        stale={false}
        onPick={vi.fn()}
        onKeepOriginal={onKeepOriginal}
        onWrite={vi.fn()}
        onRegenerate={onRegenerate}
        referenceCount={2}
        onFindReferences={vi.fn()}
      />,
    );
    expect(screen.getByText("추천 0건")).toBeInTheDocument();
    expect(screen.getByTestId("plan-reference-hint")).toHaveTextContent("지금 고른 참고 논문 2건");
    const actions = screen.getByTestId("plan-empty-actions");
    await userEvent.click(within(actions).getByRole("button", { name: "과제안 다시 만들기" }));
    expect(onRegenerate).toHaveBeenCalledTimes(1);
    await userEvent.click(within(actions).getByRole("button", { name: "원래 아이디어로 진행" }));
    expect(onKeepOriginal).toHaveBeenCalledTimes(1);
    expect(container.textContent).not.toMatch(/reference|retry_used|hint/);
    await expectNoA11yViolations(container);
  });

  it("hint 가 없으면 안내·다시 만들기 단추를 0건 자리에 두지 않는다", () => {
    renderWithProviders(
      <PlanCards
        rec={{ ...ZERO, hint: null, retry_used: false }}
        waiting={{ pending: false, elapsed: 0, cancelled: false, onCancel: vi.fn() }}
        chosenIndex={null}
        stale={false}
        onPick={vi.fn()}
        onKeepOriginal={vi.fn()}
        onWrite={vi.fn()}
        onRegenerate={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("plan-reference-hint")).toBeNull();
    expect(screen.queryByTestId("plan-retry-note")).toBeNull();
    expect(within(screen.getByTestId("plan-empty-actions")).queryByRole("button", { name: "과제안 다시 만들기" })).toBeNull();
  });
});
