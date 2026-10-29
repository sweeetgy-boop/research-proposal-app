/** 연구 작업실(홈) — 로그인 전(히어로·시작 안내·로그인 카드, 세션 API 호출 없음) / 0건 / 작성 중 / 공용 계정 안내. */
import { fireEvent, screen, within } from "@testing-library/react";
import type { RunState } from "@/api/types";
import { clearSession, setSession } from "@/auth/session";
import drafted from "@/test/fixtures/run_drafted.json";
import { expectNoA11yViolations, mockFetch, renderWithProviders } from "@/test/utils";
import Home from "./Home";
import Runs from "./Runs";
import Guide from "./Guide";

const base = drafted as unknown as RunState;
const run = (id: string, status: string, updated: string, title: string): RunState => ({
  ...base,
  run_id: id,
  status: status as RunState["status"],
  updated_at: updated,
  title,
  task_type: "응용연구",
  flow: { ...base.flow, has_working: false },
});
const RUNS = [
  run("20260101000000-00000001", "drafted", "2026-10-28T01:00:00Z", "궤도 틀림 진행 예측"),
  run("20260101000000-00000002", "finalized", "2026-10-29T01:00:00Z", "전차선 마모 점검"),
  run("20260101000000-00000003", "final_reviewing", "2026-10-27T01:00:00Z", "가선 장력 진단"),
];

afterEach(() => {
  vi.unstubAllGlobals();
  clearSession();
});

describe("연구 작업실 홈", () => {
  it("로그인 전: 히어로·시작 안내·로그인 카드만, API 를 부르지 않는다", async () => {
    const { calls } = mockFetch({});
    const { container } = renderWithProviders(<Home />);
    expect(screen.getByRole("heading", { name: /Research Studio/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "제안서 작성, 이렇게 시작하세요" })).toBeInTheDocument();
    expect(screen.getByTestId("home-login")).toBeInTheDocument();
    expect(screen.queryByText("연구 한눈에 보기")).toBeNull();
    expect(screen.queryByText("최근 제안서")).toBeNull();
    expect(screen.queryByRole("link", { name: /이어서 작성하기/ })).toBeNull();
    expect(calls.filter((c) => c.url.includes("/v1/"))).toEqual([]);
    await expectNoA11yViolations(container);
  });

  it("0건: [새 제안서]가 주 버튼이고 이어서 작성하기는 없다", async () => {
    setSession("csrf", "staff", "직원");
    mockFetch({ "/v1/runs": { runs: [] } });
    renderWithProviders(<Home />);
    expect(await screen.findByText("아직 만든 제안서가 없습니다. [새 제안서]에서 시작하세요.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /이어서 작성하기/ })).toBeNull();
    const hero = screen.getByRole("region", { name: /Research Studio/ });
    expect(within(hero).getByRole("link", { name: /새 제안서/ })).toHaveAttribute("href", "/new");
    expect(screen.getByTestId("overview-all").textContent).toContain("0");
  });

  it("작성 중: 건수·표·이어서 작성하기(가장 최근 작성 중의 지금 단계), 탭·검색", async () => {
    setSession("csrf", "staff", "직원");
    mockFetch({ "/v1/runs": { runs: RUNS } });
    const { container } = renderWithProviders(<Home />);
    expect(await screen.findByRole("link", { name: /이어서 작성하기/ })).toHaveAttribute("href", "/runs/20260101000000-00000001/edit");
    expect(screen.getByTestId("overview-all").textContent).toMatch(/3\s*편/);
    expect(screen.getByTestId("overview-writing").textContent).toMatch(/2\s*편/);
    expect(screen.getByTestId("overview-done").textContent).toMatch(/1\s*편/);
    const rows = within(screen.getByTestId("run-rows")).getAllByRole("listitem");
    expect(rows[0]!.textContent).toContain("전차선 마모 점검");
    expect(rows[0]!.textContent).toContain("응용연구");
    expect(rows[0]!.textContent).toContain("마무리 완료");
    expect(screen.queryByText(/20260101000000/)).toBeNull(); // 홈 표에는 작성 번호 없음
    expect(screen.getByText("제안서는 연구원 서버에 저장됩니다.")).toBeInTheDocument();
    expect(screen.queryByTestId("guest-notice")).toBeNull();

    fireEvent.click(screen.getByRole("tab", { name: /완료/ }));
    expect(within(screen.getByTestId("run-rows")).getAllByRole("listitem")).toHaveLength(1);
    fireEvent.click(screen.getByRole("tab", { name: /전체/ }));
    fireEvent.change(screen.getByLabelText("제안서 제목 검색"), { target: { value: "가선" } });
    expect(within(screen.getByTestId("run-rows")).getAllByRole("listitem")).toHaveLength(1);
    await expectNoA11yViolations(container);
  });

  it("공용 계정: 함께 쓰는 사람에게 보인다는 안내", async () => {
    setSession("csrf", "guest", "공용 계정");
    mockFetch({ "/v1/runs": { runs: RUNS } });
    renderWithProviders(<Home />);
    expect(await screen.findByTestId("guest-notice")).toHaveTextContent("공용 계정의 제안서는 함께 쓰는 사람에게 보입니다.");
  });

  it("⋯ 메뉴 — 이미 있는 화면 링크만, Esc 로 닫힘", async () => {
    setSession("csrf", "staff", "직원");
    mockFetch({ "/v1/runs": { runs: RUNS } });
    renderWithProviders(<Home />);
    const btn = await screen.findByRole("button", { name: "「궤도 틀림 진행 예측」 메뉴" });
    fireEvent.click(btn);
    expect(screen.getByRole("link", { name: "진행 상황" })).toHaveAttribute("href", "/runs/20260101000000-00000001");
    expect(screen.getByRole("link", { name: "초안 보기" })).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("link", { name: "진행 상황" }), { key: "Escape" });
    expect(screen.queryByRole("link", { name: "진행 상황" })).toBeNull();
  });
});

describe("내 제안서·작성 가이드", () => {
  it("내 제안서: 같은 줄 모양 + 작성 번호", async () => {
    setSession("csrf", "staff", "직원");
    mockFetch({ "/v1/runs": { runs: RUNS } });
    const { container } = renderWithProviders(<Runs />);
    expect(await screen.findByText("20260101000000-00000002")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "내 제안서" })).toBeInTheDocument();
    expect(within(screen.getByTestId("run-rows")).getAllByRole("listitem")).toHaveLength(3);
    await expectNoA11yViolations(container);
  });

  it("작성 가이드: 사용자용 네 부분, 운영자용은 없음", async () => {
    mockFetch({});
    const { container } = renderWithProviders(<Guide />);
    for (const name of ["사용 순서", "알려진 제약", "오류·개선점 기록 방법", "그림(인포그래픽) 안내"]) {
      expect(screen.getByRole("heading", { level: 2, name })).toBeInTheDocument();
    }
    expect(screen.queryByText(/launchctl|rra auth|운영자/)).toBeNull();
    await expectNoA11yViolations(container);
  });
});
