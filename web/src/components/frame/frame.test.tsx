/** 화면 틀 — 경로 표시 규칙, 사이드바(메뉴·건수·로그인 종류·공용 계정 안내), 좁은 화면 접는 메뉴. axe 0. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { clearSession, setSession } from "@/auth/session";
import { expectNoA11yViolations, mockFetch, renderWithProviders } from "@/test/utils";
import { Layout } from "@/components/Layout";
import { crumbsFor } from "./crumbs";
import runsFx from "@/test/fixtures/runs.json";

afterEach(() => {
  vi.unstubAllGlobals();
  clearSession();
});

describe("경로 표시 crumbsFor", () => {
  const labels = (p: string, t?: string) => crumbsFor(p, t).map((c) => c.label);
  it("홈·새 제안서·내 제안서·제안서 안(제목·단계)", () => {
    expect(labels("/")).toEqual(["Research Studio", "연구 작업실"]);
    expect(labels("/new")).toEqual(["Research Studio", "연구 작업실", "새 제안서", "① 아이디어 입력"]);
    expect(labels("/new/precheck")).toEqual(["Research Studio", "연구 작업실", "새 제안서", "② 유사과제 확인"]);
    expect(labels("/runs")).toEqual(["Research Studio", "연구 작업실", "내 제안서"]);
    expect(labels("/runs/abc/draft", "궤도 보수 우선순위")).toEqual(["Research Studio", "연구 작업실", "내 제안서", "궤도 보수 우선순위", "③ 초안 보기"]);
    expect(labels("/runs/abc/edit", "")).toEqual(["Research Studio", "연구 작업실", "내 제안서", "제목 미정", "④ 직접 수정"]);
    expect(labels("/runs/abc/finalize", "x").at(-1)).toBe("⑥ 최종 마무리");
    expect(labels("/sources")).toEqual(["Research Studio", "연구 작업실", "자료 현황"]);
  });
  it("마지막 칸은 링크가 없고, 제안서 제목 칸은 그 제안서로", () => {
    const c = crumbsFor("/runs/abc/draft", "t");
    expect(c.at(-1)?.to).toBeUndefined();
    expect(c.at(-2)?.to).toBe("/runs/abc");
  });
});

describe("사이드바", () => {
  it("로그인 전: 메뉴·로그인 단추, 건수 없음, API(runs) 부르지 않음 (axe 0)", async () => {
    const { calls } = mockFetch({ "/healthz": { status: "ok" } });
    const { container } = renderWithProviders(<Layout />, { route: "/" });
    const nav = screen.getByRole("navigation", { name: "주 메뉴" });
    for (const name of ["연구 작업실", "새 제안서", "내 제안서"]) expect(within(nav).getByRole("link", { name })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /작성 가이드/ }).length).toBeGreaterThan(0);
    expect(screen.getByRole("group", { name: "로그인 전" })).toBeInTheDocument();
    expect(screen.getByText("제안서는 연구원 서버에 저장됩니다.")).toBeInTheDocument();
    await expectNoA11yViolations(container);
    expect(calls.some((c) => c.url.includes("/v1/runs"))).toBe(false);
  });

  it("로그인 뒤: 내 제안서 건수, 로그인 종류, 선택 메뉴 aria-current", async () => {
    setSession("c1", "staff", "직원");
    mockFetch({ "/healthz": { status: "ok" }, "/v1/runs": runsFx });
    const { container } = renderWithProviders(<Layout />, { route: "/runs" });
    const nav = screen.getByRole("navigation", { name: "주 메뉴" });
    const mine = within(nav).getByRole("link", { name: /내 제안서/ });
    expect(mine).toHaveAttribute("aria-current", "page");
    await waitFor(() => expect(within(mine).getByLabelText(`${runsFx.runs.length}건`)).toBeInTheDocument());
    expect(screen.getByRole("group", { name: "로그인 종류: 직원" })).toBeInTheDocument();
    expect(screen.queryByText("공용 계정의 제안서는 함께 쓰는 사람에게 보입니다.")).toBeNull();
    await expectNoA11yViolations(container);
  });

  it("공용 계정이면 함께 쓰는 사람에게 보인다는 안내", async () => {
    setSession("c3", "guest", "공용 계정");
    mockFetch({ "/healthz": { status: "ok" }, "/v1/runs": { runs: [] } });
    renderWithProviders(<Layout />, { route: "/" });
    expect(screen.getByText("공용 계정의 제안서는 함께 쓰는 사람에게 보입니다.")).toBeInTheDocument();
  });
});

describe("좁은 화면 메뉴", () => {
  it("메뉴 열기 → 대화상자 안 메뉴, 닫기", async () => {
    mockFetch({ "/healthz": { status: "ok" } });
    const { container } = renderWithProviders(<Layout />, { route: "/" });
    const btn = screen.getByRole("button", { name: "메뉴 열기" });
    expect(btn).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(btn);
    const menu = await screen.findByRole("dialog", { name: "메뉴" });
    expect(within(menu).getByRole("link", { name: "새 제안서" })).toBeInTheDocument();
    await expectNoA11yViolations(container);
    await userEvent.click(within(menu).getByRole("button", { name: "메뉴 닫기" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "메뉴 열기" })).toHaveAttribute("aria-expanded", "false"));
  });
});
