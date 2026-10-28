/** 화면 하단 배포 버전 — /healthz 의 version 을 보여 주고, 없으면 표시하지 않는다. */
import { screen, waitFor } from "@testing-library/react";
import { mockFetch, renderWithProviders } from "@/test/utils";
import { clearSession } from "@/auth/session";
import { Layout } from "./Layout";
import { formatDeployedAt } from "@/lib/deployVersion";

afterEach(() => {
  vi.unstubAllGlobals();
  clearSession();
});

describe("배포 버전 표시", () => {
  it("healthz 의 커밋·배포 시각을 하단에 보여 준다", async () => {
    mockFetch({
      "/healthz": { status: "ok", version: { commit: "d65d75b789a1", short: "d65d75b", deployed_at: "2026-10-28T09:34:00+09:00", prs: ["#61"] } },
    });
    renderWithProviders(<Layout />, { route: "/login" });
    const footer = await screen.findByTestId("deploy-version");
    expect(footer.textContent).toContain("버전 d65d75b");
    expect(footer.textContent).toContain(`배포 ${formatDeployedAt("2026-10-28T09:34:00+09:00")}`);
  });

  it("version 이 없거나 healthz 가 실패하면 표시하지 않는다", async () => {
    mockFetch({ "/healthz": { status: "ok" } });
    renderWithProviders(<Layout />, { route: "/login" });
    await waitFor(() => expect(screen.getByText(/제안자가 확인한 뒤에만/)).toBeInTheDocument());
    expect(screen.queryByTestId("deploy-version")).toBeNull();
  });

  it("formatDeployedAt 은 월-일 시:분, 잘못된 값은 그대로", () => {
    expect(formatDeployedAt("2026-10-28T09:34:00+09:00")).toMatch(/^\d{2}-\d{2} \d{2}:\d{2}$/);
    expect(formatDeployedAt("x")).toBe("x");
  });
});
