/** [4] 실시간 검색 — 자료원별 상태 패널: 상태 라벨 전부·안내(비신뢰)·검색어 접기·검색 중 안내. */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations, renderWithProviders } from "@/test/utils";
import type { LiveSearch } from "@/api/types";
import { LiveSearchPanel } from "./LiveSearchPanel";

const NOTICE = "NTIS 는 등록된 서버 IP 에서만 조회됩니다. <b>관리자</b>에게 IP 등록을 요청하십시오.";

const live: LiveSearch = {
  status: "partial",
  keywords: { ko: ["궤도 틀림", "검측 이력"], en: ["track geometry", "maintenance priority"] },
  sources: [
    { source: "scienceon", status: "ok", count: 12, seconds: 1.234, notice: null },
    { source: "ntis", status: "ip_blocked", count: 0, seconds: 0.4, notice: NOTICE },
    { source: "openalex", status: "timeout", count: 0, seconds: 8, notice: null },
  ],
};

describe("실시간 검색 패널", () => {
  it("자료원별 결과 수·상태·걸린 시간, NTIS 안내는 텍스트로만, 검색어는 접혀 있다 (axe 0)", async () => {
    const { container } = renderWithProviders(<LiveSearchPanel live={live} />);
    const section = screen.getByRole("region", { name: /실시간 검색/ });
    expect(within(section).getByText("일부 완료")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "자료원별 상태" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((r) => r.textContent)).toEqual(["ScienceON12건완료1.2초", "NTIS0건IP 차단0.4초", "OpenAlex0건시간 초과8.0초"]);
    // 안내는 HTML 로 해석하지 않는다
    expect(screen.getByText(NOTICE)).toBeInTheDocument();
    expect(container.querySelector("b")).toBeNull();
    // 검색어: details 접힘 → 펼치면 국문·영문
    const details = screen.getByText("검색어").closest("details")!;
    expect(details).not.toHaveAttribute("open");
    await userEvent.click(screen.getByText("검색어"));
    expect(details).toHaveAttribute("open");
    expect(within(details).getByText("궤도 틀림")).toBeInTheDocument();
    expect(within(details).getByText("track geometry")).toBeInTheDocument();
    expect(within(section).getByRole("status")).toHaveTextContent("");
    await expectNoA11yViolations(container);
  });

  it("상태 라벨: 완료·시간 초과·IP 차단·오류·꺼짐 (꺼짐은 결과 수·시간 대신 —)", () => {
    renderWithProviders(
      <LiveSearchPanel
        live={{
          status: "done",
          keywords: { ko: [], en: [] },
          sources: [
            { source: "scienceon", status: "ok", count: 3, seconds: 0.5, notice: null },
            { source: "ntis", status: "error", count: 0, seconds: 0.1, notice: null },
            { source: "openalex", status: "off", count: 0, seconds: 0, notice: null },
            { source: "kipris", status: "timeout", count: 0, seconds: 5, notice: null },
            { source: "x", status: "ip_blocked", count: 0, seconds: 0.2, notice: null },
          ],
        }}
      />,
    );
    const table = screen.getByRole("table", { name: "자료원별 상태" });
    for (const label of ["완료", "오류", "꺼짐", "시간 초과", "IP 차단"]) expect(within(table).getByText(label)).toBeInTheDocument();
    expect(within(table).getAllByRole("row")[3]).toHaveTextContent("OpenAlex—꺼짐—");
    expect(screen.queryByText("검색어")).toBeNull(); // 검색어가 없으면 접기도 없다
    expect(screen.queryByRole("list", { name: "자료원 안내" })).toBeNull();
  });

  it("검색 중이면 polite 상태 줄, 꺼짐이면 저장된 자료만 확인했다는 안내", async () => {
    const { container, unmount } = renderWithProviders(<LiveSearchPanel live={{ status: "pending", keywords: { ko: ["궤도"], en: [] }, sources: [] }} />);
    const region = screen.getByRole("region", { name: /실시간 검색/ });
    const status = within(region).getByRole("status");
    expect(status).toHaveTextContent("실시간 검색 중…");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(region).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("table")).toBeNull();
    await expectNoA11yViolations(container);
    unmount();
    renderWithProviders(<LiveSearchPanel live={{ status: "off", keywords: { ko: [], en: [] }, sources: [] }} />);
    expect(within(screen.getByRole("region", { name: /실시간 검색/ })).getByRole("status")).toHaveTextContent("실시간 검색이 꺼져 있어");
  });
});
