/** ② 유사과제 흐름 (레인 A) — 행별 선택·AI 판정 안내·비교표·과제안 카드·직접 고치기·다음 버튼 사유. axe 0. */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations, mockFetch, renderWithProviders } from "@/test/utils";
import { clearSession } from "@/auth/session";
import { getIdea, resetIdea, updateIdea } from "@/features/idea/store";
import { emptyRequest } from "@/lib/validation";
import Precheck from "@/routes/Precheck";
import type { ComparisonFlow, PlanRecommendations, PrecheckAlert, PrecheckFlowOut, PrecheckOut } from "@/api/types";
import { SimilarRowsTable } from "./SimilarRowsTable";
import { JudgmentNotice } from "./JudgmentNotice";
import { ComparisonView } from "./ComparisonView";
import { PlanCards } from "./PlanCards";
import { PlanEditor } from "./PlanEditor";
import { effectiveBlocking, released } from "./model";

afterEach(() => {
  vi.unstubAllGlobals();
  clearSession();
  resetIdea();
});

const alert = (over: Partial<PrecheckAlert>): PrecheckAlert => ({
  doc_id: "own:1",
  title: "궤도 상태 자동 감지 연구",
  tier: "own",
  similarity: 0.86,
  blocking: false,
  basis: "summary",
  keywords: ["궤도"],
  status: null,
  own_detail: "institute",
  tier_label: "사내(철도연구원)",
  rerank_score: 0.97,
  judgment: "partial",
  judgment_label: "일부 겹침",
  judgment_reason: "대상은 같으나 방법이 다름",
  judged_by: "argon",
  merged_ids: [],
  ...over,
});
const ALERTS = [
  alert({ doc_id: "alio:proc", title: "해외 철도차량 조달정책 분석", blocking: true, judgment: "same", judgment_label: "같다", merged_ids: ["alio:proc2"] }),
  alert({ doc_id: "own:2", title: "궤도 틀림 진행 예측", judgment: "different", judgment_label: "다르다" }),
];
const request = { ...emptyRequest(), current_state: "a", root_cause: "b", limitation: "c", goal: "원래 목표", title_hint: "원래 가제" };
const CARDS: PlanRecommendations = {
  id: "rec-session-1234",
  skipped_reason: null,
  no_recommendation_reason: null,
  provider: "gemini",
  model: "argon",
  fallback_local: false,
  transfer: { public_doc_ids: [], internal_doc_ids: [], excluded_doc_ids: [], calls: 1 },
  regenerated: true,
  recommendations: [
    {
      index: 0,
      title: "진행 속도 추정 과제",
      summary: "요약",
      goal: "구간별 진행 속도 추정",
      method: "검측 이력 분석",
      scope: "일반철도",
      differentiation: "기존 과제는 감지에 그침",
      reasons: [],
      build_on: "",
      risks: "",
      compared_with: ["own:2"],
      evidence: ["own:2"],
      overlap_warning: [],
    },
    {
      index: 1,
      title: "보수 주기 산정 과제",
      summary: "요약 2",
      differentiation: "기간을 봄",
      reasons: [],
      build_on: "",
      risks: "",
      compared_with: [],
      evidence: [],
      overlap_warning: [],
    },
  ],
  discarded: [{ title: "지어낸 수치 안", reason: "unsupported_number", reason_label: "자료에 없는 수치를 씀" }],
};
const PRE: PrecheckFlowOut = {
  notice: "참고 자료",
  blocking: true,
  alerts: ALERTS,
  judgment: { status: "ai", judged_by: "argon", judged_by_label: "Argon", message: "Argon 이 판정했습니다 — '같다' 만 차단합니다.", retry_available: false, candidates: 2, provider: "gemini", model: "argon", calls: 1 },
  core_keywords: ["궤도 틀림"],
  recommendations: CARDS,
};
const TABLE: ComparisonFlow = {
  aspects: [
    { key: "objective", label: "연구목표" },
    { key: "method", label: "연구방법" },
    { key: "scope", label: "적용범위" },
    { key: "outcome", label: "기대성과" },
    { key: "differentiation", label: "차별화 방향" },
  ],
  proposal: { doc_id: null, title: "원래 가제", tier: null, similarity: null, blocking: false, basis: null, title_only: false, cells: { objective: "원래 목표", method: "검측 이력 분석", scope: "정보 없음", outcome: "정보 없음", differentiation: "기간을 봄" } },
  projects: [{ doc_id: "own:2", title: "궤도 틀림 진행 예측", tier: "own", similarity: 0.86, blocking: false, basis: "summary", title_only: false, cells: { objective: "진행 속도를 예측함.", method: "정보 없음", scope: "정보 없음", outcome: "정보 없음", differentiation: "—" } }],
  extraction: "ai",
  extraction_label: "기존 과제 칸은 Argon 가 요약·초록 원문에서 뽑은 문장입니다(원문 밖 내용 없음).",
};

describe("② 행별 선택 규칙", () => {
  it("차단 행을 모두 [관련 없음] 으로 고르면 차단 해제", () => {
    expect(effectiveBlocking(ALERTS, {})).toBe(true);
    expect(effectiveBlocking(ALERTS, { "alio:proc2": "unrelated" })).toBe(false); // 묶인 doc_id 로 골라도
    expect(released(ALERTS, { "alio:proc": "unrelated" })).toBe(true);
  });
});

describe("② 화면 조각", () => {
  it("유사과제 표 — AI 판정 이유·같은 제목 묶음·[유사함]/[관련 없음] (axe 0)", async () => {
    const onChoose = vi.fn();
    const { container } = renderWithProviders(<SimilarRowsTable alerts={ALERTS} choices={{ "own:2": "similar" }} onChoose={onChoose} />);
    const row = screen.getByRole("group", { name: "해외 철도차량 조달정책 분석 선택" });
    await userEvent.click(within(row).getByRole("button", { name: "관련 없음" }));
    expect(onChoose).toHaveBeenCalledWith("alio:proc", "unrelated");
    expect(screen.getByText("같다")).toBeInTheDocument();
    expect(screen.getByText(/같은 제목 2건 묶음/)).toBeInTheDocument();
    const similar = within(screen.getByRole("group", { name: "궤도 틀림 진행 예측 선택" })).getByRole("button", { name: "유사함" });
    expect(similar).toHaveAttribute("aria-pressed", "true");
    expect(container.textContent).not.toMatch(/unrelated|similar|partial/);
    await expectNoA11yViolations(container);
  });

  it("AI 판정 실패면 '규칙 기준' 안내와 [다시 시도]", async () => {
    const onRetry = vi.fn();
    const { container } = renderWithProviders(
      <JudgmentNotice
        judgment={{ ...PRE.judgment!, status: "rule_fallback", judged_by: "rule", message: "AI 판정 실패 — 규칙 기준", retry_available: true }}
        onRetry={onRetry}
        retrying={false}
      />,
    );
    expect(screen.getByText("AI 판정 실패 — 규칙 기준")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    expect(onRetry).toHaveBeenCalled();
    await expectNoA11yViolations(container);
  });

  it("비교표 — 고른 과제가 없으면 안내, 있으면 표와 좁은 화면 카드 (axe 0)", async () => {
    const { rerender, container } = renderWithProviders(<ComparisonView data={{ ...TABLE, projects: [], empty_reason: "유사한 과제를 고르면 비교표가 만들어집니다" }} />);
    expect(screen.getByText("유사한 과제를 고르면 비교표가 만들어집니다")).toBeInTheDocument();
    rerender(<ComparisonView data={TABLE} />);
    expect(screen.getByRole("table", { name: /차별성 비교표/ })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: /과제별 카드/ })).toBeInTheDocument();
    expect(screen.getAllByText("원래 가제").length).toBeGreaterThan(0);
    expect(screen.queryByText(/가제 없음/)).toBeNull();
    await expectNoA11yViolations(container);
  });

  it("과제안 카드 — 다섯 칸·근거·제외 사유·[과제안 다시 만들기] (axe 0)", async () => {
    const onPick = vi.fn();
    const onRegenerate = vi.fn();
    const { container } = renderWithProviders(
      <PlanCards rec={CARDS} loading={false} chosenIndex={null} stale onPick={onPick} onKeepOriginal={vi.fn()} onWrite={vi.fn()} onRegenerate={onRegenerate} />,
    );
    expect(screen.getByText("구간별 진행 속도 추정")).toBeInTheDocument();
    expect(screen.getByText("검측 이력 분석")).toBeInTheDocument();
    expect(screen.getByText(/검증에서 제외된 안 1건/)).toBeInTheDocument();
    expect(screen.getByText(/자료에 없는 수치를 씀/)).toBeInTheDocument();
    expect(screen.getByText(/유사함으로 고른 과제가 바뀌었습니다/)).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "이 안으로 진행" })[0]!);
    expect(onPick).toHaveBeenCalledWith(CARDS.recommendations[0]);
    await userEvent.click(screen.getByRole("button", { name: "과제안 다시 만들기" }));
    expect(onRegenerate).toHaveBeenCalled();
    expect(container.textContent).not.toContain("unsupported_number");
    await expectNoA11yViolations(container);
  });

  it("직접 고치기 — 칸 하나만 [AI로 다듬기], 원래 아이디어와 비교 (axe 0)", async () => {
    const { calls } = mockFetch({
      "/v1/precheck/plan/polish": { notice: "", field: "goal", text: "다듬은 목표임", changed: true, by: "argon", by_label: "Argon", reason: null },
    });
    const onConfirm = vi.fn();
    const fields = { title_hint: "원래 가제", goal: "원래 목표", method: "", scope: "", differentiation: "" };
    const { container } = renderWithProviders(<PlanEditor request={request} initial={fields} original={fields} onConfirm={onConfirm} onCancel={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "연구목표 AI로 다듬기" }));
    expect(await screen.findByDisplayValue("다듬은 목표임")).toBeInTheDocument();
    expect(JSON.parse(String(calls[0]!.init!.body)).field).toBe("goal");
    expect(screen.getByText("Argon 가 다듬었습니다.")).toBeInTheDocument();
    expect(screen.getByText("원래 아이디어와 다른 칸 1개")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "이 내용으로 확정" }));
    expect(onConfirm.mock.calls[0]![0].goal).toBe("다듬은 목표임");
    await expectNoA11yViolations(container);
  });
});

describe("② 화면 전체", () => {
  it("다음 버튼이 막히면 이유를 보이고, 차단 행을 [관련 없음] 으로 고르면 풀린다 — 카드 고르면 입력·버전 반영", async () => {
    mockFetch({
      "/v1/precheck/comparison": { notice: "", comparison: { ...TABLE, projects: [], empty_reason: "유사한 과제를 고르면 비교표가 만들어집니다" } },
      "/v1/precheck/recommendations/rec-session-1234/apply": { notice: "", index: 0, changed: [], before: {}, after: {}, request },
    });
    updateIdea({ precheck: PRE as unknown as PrecheckOut, request });
    const { container } = renderWithProviders(<Precheck />, { route: "/new/precheck" });
    const next = screen.getByRole("button", { name: /다음: 선행연구 브리핑/ });
    expect(next).toBeDisabled();
    expect(screen.getByText(/차단 경보를 확인해 주세요/)).toBeInTheDocument();
    const row = screen.getByRole("group", { name: "해외 철도차량 조달정책 분석 선택" });
    await userEvent.click(within(row).getByRole("button", { name: "관련 없음" }));
    expect(next).toBeEnabled();
    expect(screen.getByText(/차단 경보를 풀었습니다/)).toBeInTheDocument();
    expect(screen.queryByText(/차단 경보를 확인해 주세요/)).toBeNull();
    await userEvent.click(screen.getAllByRole("button", { name: "이 안으로 진행" })[0]!);
    expect((await screen.findAllByText(/과제안 1번을 입력에 반영했습니다/)).length).toBeGreaterThan(0);
    const state = getIdea();
    expect(state.request.method).toBe("검측 이력 분석");
    expect(state.request.title_hint).toBe("진행 속도 추정 과제");
    expect(state.request.idea_versions?.map((v) => v.kind)).toEqual(["original", "card"]);
    expect(state.similarChoices).toEqual({ "alio:proc": "unrelated" });
    await expectNoA11yViolations(container);
  });
});
