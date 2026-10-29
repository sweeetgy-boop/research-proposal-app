/** ① 아이디어 입력 — 정책 근거 추천 팝업 (ADR 0052): 네 칸이 채워지면 자동으로 열리고, 1순위는 미리 체크,
 *  다른 추천 추가 + 직접 입력 → [적용] 해야만 정책 근거 칸에 들어간다. [나중에 넣기]·추천 0건·[다음] 때 열기. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useLocation } from "react-router";
import { expectNoA11yViolations, mockFetch, problem, renderWithProviders } from "@/test/utils";
import { getIdea, resetIdea, updateIdea } from "@/features/idea/store";
import { formatPolicyQuote, mergePolicyBasis } from "@/api/policySuggestions";
import { POLICY_LATER_NOTE, POLICY_UNAVAILABLE } from "@/features/idea/PolicyPickDialog";
import { emptyRequest } from "@/lib/validation";
import { hasInternalId } from "@/lib/docRefs";
import structureFx from "@/test/fixtures/structure.json";
import precheckFx from "@/test/fixtures/precheck.json";
import Idea from "./Idea";

const FULL = { ...structureFx, fields: { current_state: "궤도 틀림이 반복 발생함.", root_cause: "다짐 효과가 오래 가지 않음", limitation: "주기 보수로는 진행 속도를 반영하지 못함", goal: "검측 이력 기반 보수 우선순위 산정" }, questions: [], complete: true };
const row = (rank: number, doc_id: string, title: string, quote: string) => ({ rank, doc_id, title, source: "molit", source_label: "국토교통부", year: 2025, page: null, quote, url: `https://www.molit.go.kr/${rank}` });
// 서버는 관련도 순(rank)으로 준다 — 순서가 섞여 와도 화면은 rank 순, 1순위가 "기본 추천"
const SUGGESTIONS = {
  notice: "비신뢰",
  count: 3,
  suggestions: [row(2, "bai:a1", "유지관리 실태 감사", "궤도 보수가 주기 위주라 대응이 늦음."), row(1, "molit:p1", "철도 안전 강화 계획", "노후 궤도 검측을 고도화함."), row(3, "korail_web:s1", "중장기 경영목표", "데이터 기반 유지보수로 효율을 높임.")],
};

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>;
}
function renderIdea() {
  return renderWithProviders(
    <Routes>
      <Route path="/new" element={<Idea />} />
      <Route path="*" element={<Where />} />
    </Routes>,
    { route: "/new" },
  );
}
const dialog = () => screen.getByRole("dialog", { name: "정책 근거 추천" });

async function fillByQuick() {
  await userEvent.type(screen.getByLabelText(/아이디어를 한두 문장으로/), "궤도 틀림이 반복됨. 검측 이력으로 보수 우선순위를 정하고 싶음.");
  await userEvent.click(screen.getByRole("button", { name: "네 칸으로 나누기" }));
  await userEvent.click(await screen.findByRole("button", { name: /상세 입력에 채우기/ }));
}

beforeEach(() => resetIdea());
afterEach(() => vi.unstubAllGlobals());

describe("① 정책 근거 추천 팝업", () => {
  it("네 칸 채움 → 팝업 자동 열림 → 1순위 기본 체크 → 추가 체크 + 직접 입력 → [적용] → 칸에 모두(중복 없이), axe 0", async () => {
    const { calls } = mockFetch({ "/v1/ideas/structure": FULL, "/v1/ideas/policy-suggestions": SUGGESTIONS });
    const { container } = renderIdea();
    await fillByQuick();
    const d = await screen.findByRole("dialog", { name: "정책 근거 추천" });
    // 열리자마자 부른다 — 네 칸이 들어간 입력으로
    await within(d).findByText("“노후 궤도 검측을 고도화함.”");
    const sent = JSON.parse(String(calls.find((c) => c.url === "/v1/ideas/policy-suggestions")?.init?.body)) as Record<string, string>;
    expect(sent.goal).toBe(FULL.fields.goal);
    const boxes = within(d).getAllByRole("checkbox");
    expect(boxes).toHaveLength(3);
    // rank 순: 1순위가 맨 위, 미리 체크 + "기본 추천" 배지 (자동 저장 아님 — 칸은 아직 비어 있다)
    expect(boxes[0]).toHaveAccessibleName("“노후 궤도 검측을 고도화함.”");
    expect(boxes[0]).toBeChecked();
    expect(boxes[1]).not.toBeChecked();
    expect(within(d).getAllByText("기본 추천")).toHaveLength(1);
    expect(getIdea().request.policy_basis).toBe("");
    expect(within(d).getAllByRole("link", { name: /원문/ })[0]).toHaveAttribute("href", "https://www.molit.go.kr/1");
    expect(hasInternalId(d.textContent)).toBe(false);
    await expectNoA11yViolations(container);

    await userEvent.click(boxes[2]!);
    // 직접 입력: 1순위와 같은 문장 한 줄(중복) + 새 줄
    await userEvent.type(within(d).getByLabelText("직접 입력 (선택)"), `${formatPolicyQuote({ quote: "노후 궤도 검측을 고도화함.", document: "철도 안전 강화 계획", year: 2025, page: null })}{enter}제5차 국가철도망 구축계획 — 유지보수 첨단화`);
    await userEvent.click(within(d).getByRole("button", { name: /^적용/ }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "정책 근거 추천" })).toBeNull());
    expect(getIdea().request.policy_basis).toBe(
      ["“노후 궤도 검측을 고도화함.” (철도 안전 강화 계획, 2025)", "“데이터 기반 유지보수로 효율을 높임.” (중장기 경영목표, 2025)", "제5차 국가철도망 구축계획 — 유지보수 첨단화"].join("\n"),
    );
    expect(document.getElementById("f-policy_basis")).toHaveValue(getIdea().request.policy_basis);
  });

  it("[나중에 넣기] → 칸은 비어 있고 안내, [다음] 에서 다시 묻지 않는다", async () => {
    const { calls } = mockFetch({ "/v1/ideas/structure": FULL, "/v1/ideas/policy-suggestions": SUGGESTIONS, "/v1/precheck": precheckFx });
    renderIdea();
    await fillByQuick();
    await within(await screen.findByRole("dialog", { name: "정책 근거 추천" })).findByText("“노후 궤도 검측을 고도화함.”");
    await userEvent.click(within(dialog()).getByRole("button", { name: "나중에 넣기" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "정책 근거 추천" })).toBeNull());
    expect(getIdea().request.policy_basis).toBe("");
    expect(screen.getByTestId("policy-later-note")).toHaveTextContent(POLICY_LATER_NOTE);
    await userEvent.click(screen.getByRole("button", { name: "다음: 유사과제 확인" }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/new/precheck"));
    expect(calls.some((c) => c.url.startsWith("/v1/precheck"))).toBe(true);
  });

  it("추천 0건이면 직접 입력과 [나중에 넣기] 만 — 직접 적으면 [적용]", async () => {
    mockFetch({ "/v1/ideas/structure": FULL, "/v1/ideas/policy-suggestions": { suggestions: [], count: 0 } });
    renderIdea();
    await fillByQuick();
    const d = await screen.findByRole("dialog", { name: "정책 근거 추천" });
    expect(await within(d).findByText(/해당 없음/)).toBeInTheDocument();
    expect(within(d).queryAllByRole("checkbox")).toHaveLength(0);
    expect(within(d).queryByRole("button", { name: /^적용/ })).toBeNull();
    expect(within(d).getByRole("button", { name: "나중에 넣기" })).toBeInTheDocument();
    await userEvent.type(within(d).getByLabelText("직접 입력 (선택)"), "철도안전법 제5조 종합계획");
    await userEvent.click(within(d).getByRole("button", { name: /^적용/ }));
    expect(getIdea().request.policy_basis).toBe("철도안전법 제5조 종합계획");
  });

  it("정책 자료가 없으면(503) 안내 + 직접 입력만", async () => {
    mockFetch({ "/v1/ideas/structure": FULL, "/v1/ideas/policy-suggestions": () => problem(503, "꺼짐") });
    renderIdea();
    await fillByQuick();
    const d = await screen.findByRole("dialog", { name: "정책 근거 추천" });
    expect(await within(d).findByText(new RegExp(POLICY_UNAVAILABLE))).toBeInTheDocument();
    expect(within(d).queryByRole("button", { name: "다시 받기" })).toBeNull();
    expect(within(d).getByLabelText("직접 입력 (선택)")).toBeInTheDocument();
  });

  it("[다시 받기] — 이미 본 문서를 빼고 받고, 앞의 추천·체크는 그대로", async () => {
    const { calls } = mockFetch({
      "/v1/ideas/structure": FULL,
      "/v1/ideas/policy-suggestions": (init?: RequestInit) =>
        JSON.parse(String(init?.body)).exclude_doc_ids ? { suggestions: [row(1, "mofe:b1", "정부 R&D 투자 방향", "철도 안전 R&D 를 늘림.")] } : SUGGESTIONS,
    });
    renderIdea();
    await fillByQuick();
    const d = await screen.findByRole("dialog", { name: "정책 근거 추천" });
    await within(d).findByText("“노후 궤도 검측을 고도화함.”");
    await userEvent.click(within(d).getByRole("button", { name: "다시 받기" }));
    expect(await within(d).findByText("“철도 안전 R&D 를 늘림.”")).toBeInTheDocument();
    const second = calls.filter((c) => c.url === "/v1/ideas/policy-suggestions")[1]!;
    expect(JSON.parse(String(second.init?.body)).exclude_doc_ids.sort()).toEqual(["bai:a1", "korail_web:s1", "molit:p1"]);
    const boxes = within(d).getAllByRole("checkbox");
    expect(boxes).toHaveLength(4);
    expect(boxes[0]).toBeChecked(); // 첫 1순위는 그대로, 새로 받은 것은 체크하지 않는다
    expect(boxes[3]).not.toBeChecked();
    expect(within(d).getAllByText("기본 추천")).toHaveLength(1);
  });

  it("상세 입력에서 정책 근거가 빈 채 [다음] → 팝업이 먼저, [적용] 하면 그 근거로 ② 로", async () => {
    const { calls } = mockFetch({ "/v1/ideas/policy-suggestions": SUGGESTIONS, "/v1/precheck": precheckFx });
    updateIdea({ inputMode: "detail", request: { ...emptyRequest(), ...FULL.fields } });
    renderIdea();
    await userEvent.click(screen.getByRole("button", { name: "다음: 유사과제 확인" }));
    const d = await screen.findByRole("dialog", { name: "정책 근거 추천" });
    expect(within(d).getByText(/고르거나 직접 적은 뒤 유사과제 확인으로 넘어갑니다/)).toBeInTheDocument();
    expect(calls.some((c) => c.url.startsWith("/v1/precheck"))).toBe(false);
    await within(d).findByText("“노후 궤도 검측을 고도화함.”");
    await userEvent.click(within(d).getByRole("button", { name: /^적용/ }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/new/precheck"));
    const pre = calls.find((c) => c.url.startsWith("/v1/precheck"))!;
    expect(JSON.parse(String(pre.init?.body)).policy_basis).toBe("“노후 궤도 검측을 고도화함.” (철도 안전 강화 계획, 2025)");
  });

  it("정책 근거가 이미 있으면 [다음] 은 팝업 없이 바로 ②, 칸 아래 [정책 근거 추천 열기] 로 언제든 다시", async () => {
    const { calls } = mockFetch({ "/v1/ideas/policy-suggestions": SUGGESTIONS, "/v1/precheck": precheckFx });
    updateIdea({ inputMode: "detail", request: { ...emptyRequest(), ...FULL.fields, policy_basis: "철도안전 종합계획" } });
    renderIdea();
    await userEvent.click(screen.getByRole("button", { name: "정책 근거 추천 열기" }));
    expect(await screen.findByRole("dialog", { name: "정책 근거 추천" })).toBeInTheDocument();
    await userEvent.click(within(dialog()).getByRole("button", { name: "닫기" }));
    await userEvent.click(screen.getByRole("button", { name: "다음: 유사과제 확인" }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/new/precheck"));
    expect(calls.filter((c) => c.url.startsWith("/v1/precheck"))).toHaveLength(1);
  });
});

describe("정책 근거 칸 합치기", () => {
  it("기존 글 뒤에 덧붙이고 같은 문장(공백 무시)은 한 번", () => {
    expect(mergePolicyBasis("", ["가", "나"])).toBe("가\n나");
    expect(mergePolicyBasis("가\n나", ["나 ", "다\n가", "다"])).toBe("가\n나\n다");
    expect(mergePolicyBasis("  ", [""])).toBe("");
  });
  it("문구 형식 — 긴 URL 없이 인용 + (문서, 연도, 위치)", () => {
    expect(formatPolicyQuote({ document: "제4차 철도산업발전기본계획", year: 2021, page: "표 3", quote: "유지보수 과학화" })).toBe("“유지보수 과학화” (제4차 철도산업발전기본계획, 2021, 표 3)");
    expect(formatPolicyQuote({ document: "", year: null, page: null, quote: "요지" })).toBe("“요지”");
  });
});
