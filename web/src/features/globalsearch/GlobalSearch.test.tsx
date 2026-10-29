/** 위쪽 통합 검색 — 두 묶음(내 제안서·자료), 키보드(↑↓ Enter Esc, ⌘K/Ctrl+K), 빈 결과·오류 사유, 로그인 전. */
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useLocation } from "react-router";
import { expectNoA11yViolations, mockFetch, problem, renderWithProviders } from "@/test/utils";
import { clearSession, setSession } from "@/auth/session";
import { hasInternalId } from "@/lib/docRefs";
import runsFx from "@/test/fixtures/runs.json";
import { GlobalSearch } from "./GlobalSearch";
import { matchProposals, proposalPath } from "./match";

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
    {
      doc_id: "own:p-9",
      title: "궤도 보수 사내 과제",
      source: "own",
      source_label: "사내 과제",
      url: null,
      year: null,
      summary: null,
      basis: "summary",
      live: false,
      trust: "untrusted",
    },
  ],
};

function Where() {
  const loc = useLocation();
  return <p data-testid="where">{loc.pathname + loc.search}</p>;
}

function renderSearch(route = "/runs") {
  return renderWithProviders(
    <>
      <GlobalSearch />
      <Routes>
        <Route path="*" element={<Where />} />
      </Routes>
    </>,
    { route },
  );
}

const input = () => screen.getByRole("combobox", { name: "제안서·자료 통합 검색" });
const options = () => within(screen.getByRole("listbox")).queryAllByRole("option");

afterEach(() => {
  vi.unstubAllGlobals();
  clearSession();
});

describe("통합 검색", () => {
  beforeEach(() => setSession("csrf-1", "staff", "직원"));

  it("입력하면 내 제안서·자료 두 묶음과 [자료 전체 결과 보기] — 내부 번호 없음, axe 0", async () => {
    const { calls } = mockFetch({ "/v1/runs": runsFx, "/v1/search/docs": DOCS });
    const { container } = renderSearch();
    await userEvent.type(input(), "궤도 틀림");
    const docGroup = await screen.findByRole("group", { name: "자료" });
    expect(await within(docGroup).findByText("궤도 틀림 열화 예측")).toBeInTheDocument();
    expect(within(docGroup).getByText(/OpenAlex 논문/)).toBeInTheDocument();
    expect(within(docGroup).getByText(/2021년/)).toBeInTheDocument();
    const propGroup = screen.getByRole("group", { name: "내 제안서" });
    expect(within(propGroup).getByText(/검측 이력 기반 궤도 틀림/)).toBeInTheDocument();
    expect(options().at(-1)).toHaveTextContent("자료 전체 결과 보기");
    expect(input()).toHaveAttribute("aria-expanded", "true");
    expect(hasInternalId(screen.getByRole("listbox").textContent)).toBe(false);
    // 디바운스: 글자마다 부르지 않는다
    const searchCalls = calls.filter((c) => c.url.startsWith("/v1/search/docs"));
    expect(searchCalls.length).toBe(1);
    expect(searchCalls[0]!.url).toContain("limit=5");
    await expectNoA11yViolations(container);
  });

  it("↓ 로 두 묶음을 오가고 Enter 로 제안서의 현재 단계를 연다", async () => {
    mockFetch({ "/v1/runs": runsFx, "/v1/search/docs": DOCS });
    renderSearch();
    await userEvent.type(input(), "궤도");
    await screen.findByText("궤도 틀림 열화 예측");
    await userEvent.keyboard("{ArrowDown}");
    const first = options()[0]!;
    expect(first).toHaveAttribute("aria-selected", "true");
    expect(input()).toHaveAttribute("aria-activedescendant", first.id);
    await userEvent.keyboard("{ArrowDown}");
    expect(options()[1]).toHaveAttribute("aria-selected", "true"); // 자료 묶음 첫 줄
    await userEvent.keyboard("{ArrowUp}{Enter}");
    expect(screen.getByTestId("where")).toHaveTextContent("/runs/20260101000000-00000002/final-review");
    expect(input()).toHaveAttribute("aria-expanded", "false");
  });

  it("자료를 열면 근거 패널(요약·원문 링크), 닫으면 입력칸으로 돌아온다", async () => {
    mockFetch({ "/v1/runs": runsFx, "/v1/search/docs": DOCS });
    renderSearch();
    await userEvent.type(input(), "궤도");
    await userEvent.click(await screen.findByText("궤도 틀림 열화 예측"));
    const dialog = await screen.findByRole("dialog", { name: "궤도 틀림 열화 예측" });
    expect(within(dialog).getByText("궤도 틀림 열화 속도를 검측 이력으로 예측한다")).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: /원문/ })).toHaveAttribute("href", "https://openalex.org/W1");
    await userEvent.click(within(dialog).getByRole("button", { name: "닫기" }));
    await waitFor(() => expect(input()).toHaveFocus());
  });

  it("[자료 전체 결과 보기] 와 Enter(선택 없음)는 자료 검색 화면을 연다", async () => {
    mockFetch({ "/v1/runs": runsFx, "/v1/search/docs": DOCS });
    renderSearch();
    await userEvent.type(input(), "궤도");
    await screen.findByText("궤도 틀림 열화 예측");
    await userEvent.keyboard("{Enter}");
    expect(screen.getByTestId("where")).toHaveTextContent(`/search?q=${encodeURIComponent("궤도")}`);
  });

  it("Esc 는 닫기만 하고 포커스는 입력칸에 남는다", async () => {
    mockFetch({ "/v1/runs": runsFx, "/v1/search/docs": DOCS });
    renderSearch();
    await userEvent.type(input(), "궤도");
    await screen.findByText("궤도 틀림 열화 예측");
    await userEvent.keyboard("{Escape}");
    expect(input()).toHaveAttribute("aria-expanded", "false");
    expect(input()).toHaveFocus();
    expect(input()).toHaveValue("궤도");
  });

  it("Ctrl+K / ⌘K 로 어디서든 입력칸에 포커스, 빈 검색어면 최근 제안서", async () => {
    mockFetch({ "/v1/runs": runsFx });
    renderSearch();
    fireEvent.keyDown(document.body, { key: "k", ctrlKey: true });
    expect(input()).toHaveFocus();
    expect(await screen.findByRole("group", { name: "최근 제안서" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "자료" })).toBeNull();
    expect(await screen.findByText("제목 미정")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    fireEvent.keyDown(document.body, { key: "K", metaKey: true });
    expect(input()).toHaveAttribute("aria-expanded", "true");
  });

  it("맞는 결과가 없으면 묶음마다 이유를 보인다", async () => {
    mockFetch({ "/v1/runs": runsFx, "/v1/search/docs": { notice: "", docs: [] } });
    renderSearch();
    await userEvent.type(input(), "없는낱말");
    expect(await screen.findByText(/맞는 자료가 없습니다/)).toBeInTheDocument();
    expect(screen.getByText("제목이 맞는 제안서가 없습니다.")).toBeInTheDocument();
    expect(options()).toHaveLength(1); // 전체 결과 보기만
  });

  it("자료 검색이 실패하면 서버 사유를 보이고 제안서 묶음은 그대로", async () => {
    mockFetch({ "/v1/runs": runsFx, "/v1/search/docs": () => problem(503, "검색 색인을 열 수 없습니다.") });
    renderSearch();
    await userEvent.type(input(), "궤도");
    expect(await screen.findByText(/자료를 불러오지 못했습니다: 검색 색인을 열 수 없습니다\./)).toBeInTheDocument();
    expect(screen.getByText(/검측 이력 기반 궤도 틀림/)).toBeInTheDocument();
  });
});

describe("통합 검색 — 로그인 전", () => {
  it("포커스·단축키는 로그인 창으로 보내고 API 를 부르지 않는다", async () => {
    const { calls } = mockFetch({});
    renderSearch("/new");
    fireEvent.keyDown(document.body, { key: "k", ctrlKey: true });
    // 창 제공자(LoginDialogProvider)가 없는 단위 시험에서는 useRequireLogin 이 홈으로 보내며 창을 연다
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/$/);
    expect(calls).toHaveLength(0);
  });
});

describe("match", () => {
  it("제목 일치는 공백·대소문자를 무시하고 최근 수정 순", () => {
    const runs = runsFx.runs as never[];
    expect(matchProposals(runs, "궤도틀림").map((r: { run_id: string }) => r.run_id)).toEqual(["20260101000000-00000002"]);
    expect(matchProposals(runs, "", 1)).toHaveLength(1);
  });

  it("현재 단계 경로", () => {
    const p = (status: string, legacy = false) => proposalPath({ run_id: "r", status, legacy } as never);
    expect(p("running")).toBe("/runs/r");
    expect(p("drafted")).toBe("/runs/r/draft");
    expect(p("editing")).toBe("/runs/r/edit");
    expect(p("final_reviewed")).toBe("/runs/r/final-review");
    expect(p("finalized")).toBe("/runs/r/finalize");
    expect(p("finalized", true)).toBe("/runs/r");
  });
});
