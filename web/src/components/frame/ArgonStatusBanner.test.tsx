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

  it("관리자: Argon 띠 + 운영 상태 줄(터널 내려감·로컬 모델 응답 없음)이 함께 보인다", async () => {
    setSession("c5", "admin", "관리자");
    mockFetch({
      "/healthz": { ...health("unavailable"), tunnel: "down", llm: { gemini: "unavailable", since: null, local: "unavailable" } },
      "/v1/runs": { runs: [] },
    });
    const { container } = renderWithProviders(<Layout />, { route: "/runs" });
    const banner = await screen.findByTestId("argon-status-banner");
    expect(banner).toHaveTextContent(TITLE);
    await waitFor(() => expect(screen.getAllByTestId("ops-status-line")).toHaveLength(2));
    expect(banner).toHaveTextContent("외부 접속 경로(Funnel) 내려감");
    expect(banner).toHaveTextContent("로컬 모델 응답 없음");
    expect(document.body.textContent).not.toMatch(/\bdown\b|unavailable|tunnel|llm\.local/);
    await expectNoA11yViolations(container);
  });

  it.each([
    ["tunnel down", { tunnel: "down", local: "ok" }, "외부 접속 경로(Funnel) 내려감"],
    ["llm.local unavailable", { tunnel: "ok", local: "unavailable" }, "로컬 모델 응답 없음"],
  ])("관리자: Argon 은 ok 여도 %s 이면 운영 상태 줄만 보인다", async (_name, ops, line) => {
    setSession("c6", "admin", "관리자");
    mockFetch({
      "/healthz": { status: "ok", tunnel: ops.tunnel, llm: { gemini: "ok", since: null, local: ops.local } },
      "/v1/runs": { runs: [] },
    });
    renderWithProviders(<Layout />, { route: "/runs" });
    const banner = await screen.findByTestId("argon-status-banner");
    expect(banner).toHaveTextContent(line);
    expect(screen.getAllByTestId("ops-status-line")).toHaveLength(1);
    expect(screen.queryByText(TITLE)).toBeNull();
    expect(screen.queryByTestId("argon-status-reason")).toBeNull();
  });

  it.each([["staff", "직원"], ["guest", "공용 계정"]])(
    "%s: 터널 내려감·로컬 모델 응답 없음은 보이지 않는다 (관리자 전용, Argon ok 면 띠 없음)",
    async (kind, label) => {
      setSession("c7", kind, label);
      const { calls } = mockFetch({
        "/healthz": { status: "ok", tunnel: "down", llm: { gemini: "ok", since: null, local: "unavailable" } },
        "/v1/runs": { runs: [] },
      });
      renderWithProviders(<Layout />, { route: "/runs" });
      await waitFor(() => expect(calls.some((c) => c.url === "/healthz")).toBe(true));
      expect(screen.queryByTestId("argon-status-banner")).toBeNull();
      expect(document.body.textContent).not.toContain("Funnel");
    },
  );

  it("관리자: tunnel·llm.local 이 unknown 이거나 칸이 없으면 운영 상태 줄이 없다", async () => {
    setSession("c8", "admin", "관리자");
    const { calls } = mockFetch({
      "/healthz": { status: "ok", tunnel: "unknown", llm: { gemini: "ok", since: null } },
      "/v1/runs": { runs: [] },
    });
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
