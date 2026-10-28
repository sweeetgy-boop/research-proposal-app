import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations, mockFetch, problem, renderWithProviders } from "@/test/utils";
import { PolicySuggestions, POLICY_UNAVAILABLE } from "./PolicySuggestions";
import { formatPolicyQuote } from "@/api/policySuggestions";
import { emptyRequest } from "@/lib/validation";
import { hasInternalId } from "@/lib/docRefs";

afterEach(() => vi.unstubAllGlobals());
const req = {
  ...emptyRequest(),
  current_state: "궤도 틀림 반복",
  root_cause: "노반 침하",
  limitation: "임계치 초과만 보수",
  goal: "검측 이력 기반 보수 우선순위 산정",
}; // 필수 4칸이 차야 [추천 받기] 가 열린다

describe("정책 근거 추천", () => {
  it("문구 형식 — 긴 URL 없이 인용 + (문서, 연도, 위치)", () => {
    expect(formatPolicyQuote({ document: "제4차 철도산업발전기본계획", year: 2021, page: "표 3", quote: "유지보수 과학화" })).toBe("“유지보수 과학화” (제4차 철도산업발전기본계획, 2021, 표 3)");
    expect(formatPolicyQuote({ document: "", year: null, page: null, quote: "요지" })).toBe("“요지”");
  });

  it("추천 받기 → 제목·자료원 이름·원문 링크, 번호 없음 → 고른 것만 onPick, axe 통과", async () => {
    const { calls } = mockFetch({
      "/v1/ideas/policy-suggestions": {
        suggestions: [
          {
            doc_id: "molit:abc123",
            title: "제4차 국가철도망 구축계획",
            source: "molit",
            source_label: "국토교통부",
            year: 2021,
            page: "표 3",
            quote: "안전 투자 확대",
            url: "https://www.molit.go.kr/x?id=1",
          },
        ],
      },
    });
    const onPick = vi.fn();
    const { container } = renderWithProviders(<PolicySuggestions request={req} onPick={onPick} />);
    expect(calls).toHaveLength(0); // 화면을 열 때는 부르지 않는다
    await userEvent.click(screen.getByRole("button", { name: "추천 받기" }));
    expect(await screen.findByText("“안전 투자 확대”")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /제4차 국가철도망 구축계획 \(국토교통부\) 근거 보기/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /원문/ })).toHaveAttribute("href", "https://www.molit.go.kr/x?id=1");
    expect(hasInternalId(container.textContent)).toBe(false);
    expect(container.textContent).not.toContain("https://");
    await expectNoA11yViolations(container);
    await userEvent.click(screen.getByRole("button", { name: "정책 근거에 추가" }));
    expect(onPick).toHaveBeenCalledWith("“안전 투자 확대” (제4차 국가철도망 구축계획, 2021, 표 3)");
  });

  it("결과 0건이면 사유(해당 없음)와 [다시 시도]", async () => {
    mockFetch({ "/v1/ideas/policy-suggestions": { suggestions: [], count: 0 } });
    renderWithProviders(<PolicySuggestions request={req} onPick={() => undefined} />);
    await userEvent.click(screen.getByRole("button", { name: "추천 받기" }));
    expect(await screen.findByText(/해당 없음/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeInTheDocument();
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
