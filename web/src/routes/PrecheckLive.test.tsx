/** [4] ② 유사과제 확인 — 실시간 검색 배지·자료원별 상태. 필드가 없는 옛 응답이면 아무것도 늘지 않는다. */
import { screen, within } from "@testing-library/react";
import { expectNoA11yViolations, mockFetch, renderWithProviders } from "@/test/utils";
import { clearSession } from "@/auth/session";
import { resetIdea, updateIdea } from "@/features/idea/store";
import { emptyRequest } from "@/lib/validation";
import Precheck from "./Precheck";
import precheckFx from "@/test/fixtures/precheck.json";
import type { PrecheckOut } from "@/api/types";

afterEach(() => {
  vi.unstubAllGlobals();
  clearSession();
  resetIdea();
});

const base = precheckFx as PrecheckOut;
const request = { ...emptyRequest(), current_state: "a", root_cause: "b", limitation: "c", goal: "d" };

const livePre: PrecheckOut = {
  ...base,
  alerts: [
    { ...base.alerts[0]!, live: false },
    { ...base.alerts[0]!, doc_id: "ntis:live-1", title: "실시간 NTIS 과제 (가짜)", tier: "national_rnd", tier_label: "NTIS 국가R&D 과제", live: true },
  ],
  related_research: [
    { doc_id: "scienceon:live-1", title: "실시간 논문 (가짜)", source: "scienceon", source_label: "ScienceON 국내 논문·보고서", doc_type: "paper", year: 2025, similarity: 0.9, url: null, live: true },
    { doc_id: "openalex:stored-1", title: "저장된 논문 (가짜)", source: "openalex", source_label: "OpenAlex", doc_type: "paper", year: 2023, similarity: 0.85, url: null },
  ],
  live_search: {
    status: "partial",
    keywords: { ko: ["궤도 틀림"], en: ["track geometry"] },
    sources: [
      { source: "scienceon", status: "ok", count: 7, seconds: 1.5, notice: null },
      { source: "ntis", status: "ip_blocked", count: 0, seconds: 0.3, notice: "NTIS 는 등록된 서버 IP 에서만 조회됩니다." },
      { source: "openalex", status: "timeout", count: 0, seconds: 8, notice: null },
    ],
  },
};

describe("② 실시간 검색", () => {
  it("live 항목에만 '실시간 검색' 배지, 자료원별 상태 패널·NTIS 안내 (axe 0)", async () => {
    mockFetch({});
    updateIdea({ precheck: livePre, request });
    const { container } = renderWithProviders(<Precheck />, { route: "/new/precheck" });
    const table = screen.getByRole("table", { name: /유사과제 목록/ });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(within(rows[0]!).queryByText("실시간 검색")).toBeNull();
    expect(within(rows[1]!).getByText("실시간 검색")).toBeInTheDocument();
    const related = screen.getByRole("region", { name: /관련 연구 2건/ });
    const items = within(related).getAllByRole("listitem");
    expect(within(items[0]!).getByText("실시간 검색")).toBeInTheDocument();
    expect(within(items[1]!).queryByText("실시간 검색")).toBeNull();
    const status = screen.getByRole("table", { name: "자료원별 상태" });
    expect(within(status).getByText("IP 차단")).toBeInTheDocument();
    expect(within(status).getByText("시간 초과")).toBeInTheDocument();
    expect(screen.getByText("NTIS 는 등록된 서버 IP 에서만 조회됩니다.")).toBeInTheDocument();
    expect(screen.getByText("검색어")).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("옛 응답(필드 없음)이면 배지·패널이 없다", () => {
    mockFetch({});
    updateIdea({ precheck: base, request });
    renderWithProviders(<Precheck />, { route: "/new/precheck" });
    expect(screen.getByRole("heading", { name: /유사과제 1건/ })).toBeInTheDocument();
    expect(screen.queryByText("실시간 검색")).toBeNull();
    expect(screen.queryByRole("table", { name: "자료원별 상태" })).toBeNull();
  });

  it("검색 중이면 '실시간 검색 중…' 상태 줄", () => {
    mockFetch({});
    updateIdea({ precheck: { ...base, live_search: { status: "pending", keywords: { ko: [], en: [] }, sources: [] } }, request });
    renderWithProviders(<Precheck />, { route: "/new/precheck" });
    expect(screen.getByText("실시간 검색 중…")).toBeInTheDocument();
  });
});
