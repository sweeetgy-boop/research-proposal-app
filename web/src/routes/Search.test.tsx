/** 자료 검색(전체 결과) — 주소의 검색어·자료원·연도 거르기, 근거 패널, 문서 번호 숨김. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations, mockFetch, renderWithProviders } from "@/test/utils";
import sourcesFx from "@/test/fixtures/sources.json";
import Search from "./Search";

const DOCS = {
  notice: "비신뢰",
  docs: [
    {
      doc_id: "openalex:w-1",
      title: "궤도 틀림 열화 예측",
      source: "openalex",
      source_label: "OpenAlex 논문",
      url: "https://openalex.org/W1",
      year: 2021,
      summary: "궤도 틀림 열화 속도를 검측 이력으로 예측한다",
      basis: "abstract",
      live: false,
      trust: "untrusted",
    },
  ],
};

afterEach(() => vi.unstubAllGlobals());

describe("자료 검색", () => {
  it("주소의 검색어로 바로 찾고 결과는 제목·자료원·연도·발췌 — axe 0", async () => {
    const { calls } = mockFetch({ "/v1/search/docs": DOCS, "/v1/sources/status": sourcesFx });
    const { container } = renderWithProviders(<Search />, { route: "/search?q=%EA%B6%A4%EB%8F%84" });
    const list = await screen.findByTestId("search-results");
    expect(within(list).getByText("궤도 틀림 열화 예측")).toBeInTheDocument();
    expect(within(list).getByText("OpenAlex 논문")).toBeInTheDocument();
    expect(within(list).getByText(/2021년/)).toBeInTheDocument();
    expect(screen.getByLabelText("검색어")).toHaveValue("궤도");
    expect(calls.some((c) => c.url.startsWith("/v1/search/docs?q=%EA%B6%A4%EB%8F%84&limit=20"))).toBe(true);
    expect(container.textContent).not.toContain("openalex:");
    await expectNoA11yViolations(container);
  });

  it("자료원·연도 거르기는 주소와 요청에 실린다", async () => {
    const { calls } = mockFetch({ "/v1/search/docs": DOCS, "/v1/sources/status": sourcesFx });
    renderWithProviders(<Search />, { route: "/search?q=x" });
    await userEvent.click(await screen.findByRole("checkbox", { name: /OpenAlex 해외 논문/ }));
    await userEvent.type(screen.getByLabelText("시작"), "2020");
    await userEvent.type(screen.getByLabelText("끝"), "2026");
    await userEvent.click(screen.getByRole("button", { name: "연도 적용" }));
    await waitFor(() =>
      expect(calls.some((c) => c.url.includes("sources=openalex") && c.url.includes("year_from=2020") && c.url.includes("year_to=2026"))).toBe(true),
    );
    await userEvent.click(screen.getByRole("button", { name: "조건 지우기" }));
    expect(screen.getByRole("checkbox", { name: /OpenAlex 해외 논문/ })).not.toBeChecked();
  });

  it("제목을 누르면 근거 패널(요약·원문)", async () => {
    mockFetch({ "/v1/search/docs": DOCS, "/v1/sources/status": sourcesFx });
    renderWithProviders(<Search />, { route: "/search?q=x" });
    await userEvent.click(await screen.findByRole("button", { name: "궤도 틀림 열화 예측 요약 보기" }));
    const dialog = await screen.findByRole("dialog", { name: "궤도 틀림 열화 예측" });
    expect(within(dialog).getByRole("link", { name: /원문/ })).toHaveAttribute("href", "https://openalex.org/W1");
  });

  it("문서 번호로 열면(근거 패널 [원본 보기]) 번호는 입력칸·화면에 보이지 않는다", async () => {
    mockFetch({ "/v1/search/docs": DOCS, "/v1/sources/status": sourcesFx });
    const { container } = renderWithProviders(<Search />, { route: "/search?q=openalex%3Aw-1" });
    await screen.findByTestId("search-results");
    expect(screen.getByLabelText("검색어")).toHaveValue("");
    expect(container.textContent).not.toContain("openalex:w-1");
  });

  it("결과가 없으면 거르기를 넓히라는 이유", async () => {
    mockFetch({ "/v1/search/docs": { notice: "", docs: [] }, "/v1/sources/status": sourcesFx });
    renderWithProviders(<Search />, { route: "/search?q=x&year_from=2030" });
    expect(await screen.findByText(/자료원·연도 조건을 넓히거나/)).toBeInTheDocument();
  });
});
