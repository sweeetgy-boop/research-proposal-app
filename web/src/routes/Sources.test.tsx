/** 자료원 상태 화면: 차단 안내(IP 거부, 레인 I)를 표와 경고 상자에 보인다. */
import { screen } from "@testing-library/react";
import { expectNoA11yViolations, mockFetch, renderWithProviders } from "@/test/utils";
import Sources from "./Sources";
import sourcesFx from "@/test/fixtures/sources.json";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("자료원 상태", () => {
  it("IP 거부 안내가 있는 자료원은 경고 상자와 행에 같은 문구를 보인다", async () => {
    mockFetch({ "/v1/sources/status": sourcesFx });
    const { container } = renderWithProviders(<Sources />, { route: "/sources" });
    expect(await screen.findByRole("alert")).toHaveTextContent("호출이 거부된 자료원이 있습니다");
    const notices = screen.getAllByText(/현재 IP 203\.0\.113\.9 가 NTIS 국가R&D 과제 등록 IP 에 없습니다\. 활용신청에 추가하세요/);
    expect(notices.length).toBe(2); // 경고 상자 + 표 행
    expect(screen.getByText("호출 거부")).toBeInTheDocument();
    expect(screen.getByText("OpenAlex 해외 논문")).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("안내가 없으면 경고 상자를 그리지 않는다", async () => {
    const clean = { sources: sourcesFx.sources.map((s) => ({ ...s, notice: null })) };
    mockFetch({ "/v1/sources/status": clean });
    renderWithProviders(<Sources />, { route: "/sources" });
    expect(await screen.findByText("OpenAlex 해외 논문")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
