/** Argon 연결 오류 알림 띠 (ADR 0055) — /healthz llm.gemini 가 ok·unknown 이 아니면 로그인한 화면 맨 위에.
 *  사유 줄은 관리자만, 로그인 전에는 없음, 내부 코드는 화면에 없음. axe 0. */
import { act, cleanup, screen, waitFor } from "@testing-library/react";
import { clearSession, setSession } from "@/auth/session";
import { expectNoA11yViolations, mockFetch, renderWithProviders } from "@/test/utils";
import { Layout } from "@/components/Layout";
import { ARGON_POLL_MS } from "@/api/hooks";

const TITLE = "AI(Argon) 연결 오류 — 로컬 모델로 대체 중";
const health = (gemini: string | null) => ({
  status: "ok",
  ...(gemini === null ? {} : { llm: { gemini, since: "2026-11-03T16:14:49+09:00" } }),
});

afterEach(() => {
  cleanup(); // 띠를 내린 뒤 세션을 지운다 (act 경고 방지)
  vi.unstubAllGlobals();
  clearSession();
});

describe("Argon 연결 오류 알림 띠", () => {
  it("로그인 전에는 키 무효여도 띠가 없다", async () => {
    const { calls } = mockFetch({ "/healthz": health("key_invalid") });
    renderWithProviders(<Layout />, { route: "/" });
    await waitFor(() => expect(calls.some((c) => c.url === "/healthz")).toBe(true)); // 하단 버전용 조회는 그대로
    expect(screen.queryByText(TITLE)).toBeNull();
  });

  it("직원: 제목만, 사유 줄 없음 — role=status, 내부 코드 없음 (axe 0)", async () => {
    setSession("c1", "staff", "직원");
    mockFetch({ "/healthz": health("key_invalid"), "/v1/runs": { runs: [] } });
    const { container } = renderWithProviders(<Layout />, { route: "/runs" });
    const banner = await screen.findByTestId("argon-status-banner");
    expect(banner).toHaveTextContent(TITLE);
    expect(banner).toHaveAttribute("role", "status");
    expect(screen.queryByTestId("argon-status-reason")).toBeNull();
    expect(screen.queryByText("API 키 확인 필요")).toBeNull();
    expect(document.body.textContent).not.toMatch(/key_invalid|gemini|INVALID_ARGUMENT/);
    await expectNoA11yViolations(container);
  });

  it.each([
    ["key_invalid", "API 키 확인 필요"],
    ["quota", "사용 한도 초과"],
    ["unavailable", "응답 없음"],
  ])("관리자: %s → 사유 줄 '%s'", async (state, reason) => {
    setSession("c2", "admin", "관리자");
    mockFetch({ "/healthz": health(state), "/v1/runs": { runs: [] } });
    const { container } = renderWithProviders(<Layout />, { route: "/runs" });
    const banner = await screen.findByTestId("argon-status-banner");
    expect(banner).toHaveTextContent(TITLE);
    expect(screen.getByTestId("argon-status-reason")).toHaveTextContent(reason);
    expect(document.body.textContent).not.toContain(state);
    await expectNoA11yViolations(container);
  });

  it.each([["ok"], ["unknown"], [null], ["something_new"]])("%s 이면 띠가 없다", async (state) => {
    setSession("c3", "admin", "관리자");
    const { calls } = mockFetch({ "/healthz": health(state), "/v1/runs": { runs: [] } });
    renderWithProviders(<Layout />, { route: "/runs" });
    await waitFor(() => expect(calls.some((c) => c.url === "/healthz")).toBe(true));
    expect(screen.queryByTestId("argon-status-banner")).toBeNull();
  });

  it("다시 읽어 ok 가 되면 띠가 사라진다 (60초 주기)", async () => {
    expect(ARGON_POLL_MS).toBe(60_000);
    setSession("c4", "guest", "공용 계정");
    let state = "unavailable";
    mockFetch({ "/healthz": () => health(state), "/v1/runs": { runs: [] } });
    const { qc } = renderWithProviders(<Layout />, { route: "/runs" });
    await screen.findByTestId("argon-status-banner");
    state = "ok";
    await act(() => qc.refetchQueries({ queryKey: ["health"] }));
    await waitFor(() => expect(screen.queryByTestId("argon-status-banner")).toBeNull());
  });
});
