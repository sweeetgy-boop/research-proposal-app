/** 화면 안 로그인 — 로그인 전 보호 화면은 주소를 그대로 두고 로그인 창을 띄우고, 로그인하면 그 화면으로 이어진다. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { clearSession, getCsrf, setSession } from "@/auth/session";
import { RequireAuth } from "@/auth/RequireAuth";
import { ToastProvider } from "@/components/ui/toast";
import { expectNoA11yViolations, mockFetch } from "@/test/utils";
import Login from "@/routes/Login";
import { LoginDialogProvider } from "./LoginDialog";
import { useRequireLogin } from "./useRequireLogin";

afterEach(() => {
  vi.unstubAllGlobals();
  clearSession();
});

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>;
}

function HomeStub() {
  const requireLogin = useRequireLogin();
  return (
    <div>
      <h1>홈</h1>
      <button type="button" onClick={() => requireLogin("/runs")}>
        내 제안서 열기
      </button>
    </div>
  );
}

function renderApp(route: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <ToastProvider>
          <LoginDialogProvider>
            <Where />
            <Routes>
              <Route path="/" element={<HomeStub />} />
              <Route path="/login" element={<Login />} />
              <Route element={<RequireAuth />}>
                <Route path="/new" element={<h1>① 아이디어 입력</h1>} />
                <Route path="/runs" element={<h1>내 제안서 목록</h1>} />
              </Route>
            </Routes>
          </LoginDialogProvider>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function sessionOk() {
  return mockFetch({ "/v1/session": { csrf: "c9", expires_in: 10, kind: "staff", label: "직원" } });
}

describe("화면 안 로그인", () => {
  it("로그인 전 /new → 그 자리에 로그인 창, 로그인하면 같은 주소의 ① 입력 (axe 0)", async () => {
    sessionOk();
    const { container } = renderApp("/new");
    const dialog = await screen.findByRole("dialog", { name: "로그인" });
    expect(screen.getByTestId("where").textContent).toBe("/new");
    expect(screen.queryByText("① 아이디어 입력")).toBeNull();
    await expectNoA11yViolations(container);
    await userEvent.type(within(dialog).getByLabelText("사번"), "K-0001");
    await userEvent.click(within(dialog).getByRole("button", { name: "로그인" }));
    expect(await screen.findByText("① 아이디어 입력")).toBeInTheDocument();
    expect(getCsrf()).toBe("c9");
    expect(screen.getByTestId("where").textContent).toBe("/new");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("홈에서 로그인 필요한 동작 → 창 → 로그인 뒤 원래 가려던 곳으로", async () => {
    sessionOk();
    renderApp("/");
    await userEvent.click(screen.getByRole("button", { name: "내 제안서 열기" }));
    const dialog = await screen.findByRole("dialog", { name: "로그인" });
    await userEvent.type(within(dialog).getByLabelText("사번"), "K-0001");
    await userEvent.click(within(dialog).getByRole("button", { name: "로그인" }));
    expect(await screen.findByText("내 제안서 목록")).toBeInTheDocument();
    expect(screen.getByTestId("where").textContent).toBe("/runs");
  });

  it("로그인돼 있으면 창 없이 바로 이동", async () => {
    setSession("c1", "staff", "직원");
    renderApp("/");
    await userEvent.click(screen.getByRole("button", { name: "내 제안서 열기" }));
    expect(await screen.findByText("내 제안서 목록")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("옛 /login 주소 → 홈으로 넘어가며 로그인 창", async () => {
    sessionOk();
    renderApp("/login");
    expect(await screen.findByRole("dialog", { name: "로그인" })).toBeInTheDocument();
    expect(screen.getByTestId("where").textContent).toBe("/");
    expect(screen.getByRole("heading", { name: "홈" })).toBeInTheDocument();
  });

  it("창을 닫아도 보호 화면 내용은 그리지 않고 다시 여는 버튼을 둔다", async () => {
    renderApp("/runs");
    const dialog = await screen.findByRole("dialog", { name: "로그인" });
    await userEvent.click(within(dialog).getByRole("button", { name: "닫기" }));
    expect(screen.queryByText("내 제안서 목록")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "로그인 창 열기" }));
    expect(await screen.findByRole("dialog", { name: "로그인" })).toBeInTheDocument();
  });
});
