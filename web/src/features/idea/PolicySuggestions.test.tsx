import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations, mockFetch, problem, renderWithProviders } from "@/test/utils";
import { PolicySuggestions, POLICY_UNAVAILABLE } from "./PolicySuggestions";
import { formatPolicyQuote } from "@/api/policySuggestions";
import { emptyRequest } from "@/lib/validation";

afterEach(() => vi.unstubAllGlobals());
const req = {
  ...emptyRequest(),
  current_state: "궤도 틀림 반복",
  root_cause: "노반 침하",
  limitation: "임계치 초과만 보수",
  goal: "검측 이력 기반 보수 우선순위 산정",
}; // 필수 4칸이 차야 [추천 받기] 가 열린다

describe("정책 근거 추천", () => {
  it("문구 형식", () => {
    expect(formatPolicyQuote({ document: "제4차 철도산업발전기본계획", year: 2021, page: 12, quote: "유지보수 과학화", url: null })).toBe("유지보수 과학화 (제4차 철도산업발전기본계획, 2021, p.12)");
    expect(formatPolicyQuote({ document: "", year: null, page: null, quote: "요지", url: null })).toBe("요지");
  });

  it("추천 받기 → 항목 → 고른 것만 onPick, axe 통과", async () => {
    const { calls } = mockFetch({ "/v1/ideas/policy-suggestions": { items: [{ document: "기본계획", year: 2021, page: 3, quote: "안전 투자 확대", url: null }] } });
    const onPick = vi.fn();
    const { container } = renderWithProviders(<PolicySuggestions request={req} onPick={onPick} />);
    expect(calls).toHaveLength(0); // 화면을 열 때는 부르지 않는다
    await userEvent.click(screen.getByRole("button", { name: "추천 받기" }));
    expect(await screen.findByText("안전 투자 확대")).toBeInTheDocument();
    await expectNoA11yViolations(container);
    await userEvent.click(screen.getByRole("button", { name: "정책 근거에 추가" }));
    expect(onPick).toHaveBeenCalledWith("안전 투자 확대 (기본계획, 2021, p.3)");
  });

  it("404/405/503 이면 영역을 접고 안내 한 줄", async () => {
    mockFetch({ "/v1/ideas/policy-suggestions": () => problem(405, "Method Not Allowed") });
    renderWithProviders(<PolicySuggestions request={req} onPick={() => undefined} />);
    await userEvent.click(screen.getByRole("button", { name: "추천 받기" }));
    expect(await screen.findByText(POLICY_UNAVAILABLE)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "추천 받기" })).toBeNull();
  });
});


test("필수 4칸이 비면 추천 받기 버튼이 잠긴다", () => {
  renderWithProviders(<PolicySuggestions request={{ ...emptyRequest(), goal: "목표만" }} onPick={() => undefined} />);
  expect(screen.getByRole("button", { name: "추천 받기" })).toBeDisabled();
  expect(screen.getByText(/필수 4칸/)).toBeInTheDocument();
});
