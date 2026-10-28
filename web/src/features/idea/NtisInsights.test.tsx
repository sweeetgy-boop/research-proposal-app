/** ② NTIS 과제 카드 — 주요 성과(참고용)·NTIS 추천(외부 링크) 렌더, 접기/펼치기, 비신뢰 텍스트, axe. */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations, mockFetch, problem, renderWithProviders } from "@/test/utils";
import { clearSession } from "@/auth/session";
import { resetIdea, updateIdea } from "@/features/idea/store";
import { emptyRequest } from "@/lib/validation";
import { tierLabel } from "@/lib/tiers";
import { NtisInsights, OUTCOMES_SHOWN, UNAVAILABLE_HINT } from "./NtisInsights";
import { AlertsTable } from "./AlertsTable";
import Precheck from "@/routes/Precheck";
import ntisFx from "@/test/fixtures/ntis_outcomes.json";
import precheckFx from "@/test/fixtures/precheck.json";
import type { NtisOutcomesOut, OverlapAlert, PrecheckOut } from "@/api/types";

const fx = ntisFx as NtisOutcomesOut;
const req = { ...emptyRequest(), current_state: "a", root_cause: "b", limitation: "c", goal: "d" };
const ntisAlert: OverlapAlert = {
  doc_id: "ntis:1415171234",
  title: "궤도 틀림 진행 예측 국가R&D 과제",
  tier: "national_rnd",
  similarity: 0.86,
  blocking: false,
  basis: "abstract",
  keywords: ["궤도"],
  status: null,
  own_detail: null,
  tier_label: "국가R&D 과제",
};

afterEach(() => {
  vi.unstubAllGlobals();
  clearSession();
  resetIdea();
});

describe("NtisInsights", () => {
  it("과제 카드마다 주요 성과(참고용) 최대 5건 + 더 보기, 조회 실패 과제는 안내, NTIS 추천은 외부 링크, 비신뢰 텍스트는 HTML 로 해석하지 않는다", async () => {
    const { container } = renderWithProviders(<NtisInsights data={fx} />);
    const cards = screen.getAllByTestId("ntis-project");
    expect(cards).toHaveLength(2);
    const first = within(cards[0]!);
    expect(first.getByText("주요 성과 (참고용)")).toBeInTheDocument();
    expect(first.getAllByRole("listitem")).toHaveLength(OUTCOMES_SHOWN);
    expect(first.queryByText("성과 특허 2 (숨김)")).not.toBeInTheDocument();
    expect(first.getAllByText("논문")).toHaveLength(4); // kind 라벨 (보이는 5건 중 논문 4)
    expect(first.getByText("한국철도학회논문집")).toBeInTheDocument(); // venue
    expect(first.getByText("2024")).toBeInTheDocument(); // year
    // 제목의 태그는 텍스트 그대로 — 요소로 해석되지 않는다
    expect(first.getByText("궤도 틀림 진행 예측 국가R&D 과제 <b>굵게</b>")).toBeInTheDocument();
    expect(container.querySelector("b")).toBeNull();
    const more = first.getByRole("button", { name: `성과 ${fx.projects[0]!.outcomes.length - OUTCOMES_SHOWN}건 더 보기` });
    expect(more).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(more);
    expect(first.getAllByRole("listitem")).toHaveLength(fx.projects[0]!.outcomes.length);
    expect(first.getByText("성과 특허 2 (숨김)")).toBeInTheDocument();
    expect(first.getByRole("button", { name: "접기" })).toHaveAttribute("aria-expanded", "true");
    // 조회 실패 과제
    expect(within(cards[1]!).getByText(/성과를 가져오지 못했습니다 \(NtisError\)/)).toBeInTheDocument();
    // NTIS 추천: 외부 링크·미검증 표시, 새 창 + noopener
    const rec = screen.getByTestId("ntis-recommended");
    expect(within(rec).getByRole("heading", { name: "NTIS 추천" })).toBeInTheDocument();
    expect(within(rec).getByText(/외부 링크 · 미검증/)).toBeInTheDocument();
    const links = within(rec).getAllByRole("link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute("href", "https://www.ntis.go.kr/project/pjtInfo.do?pjtId=1415199001");
    expect(links[0]).toHaveAttribute("target", "_blank");
    expect(links[0]).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(rec).getByText("연관 과제 A <script>alert(1)</script>")).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
    expect(within(rec).getByText("NTIS 추천 1위")).toBeInTheDocument();
    expect(rec.textContent).not.toMatch(/점수|fake-rel/); // 과제번호·점수 숫자 없음 (ADR 0039)
    // notice 는 작은 캡션으로 보인다
    expect(screen.getByText(fx.notice)).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("조회 불가(503 등)는 한 줄 안내만, 결과가 비면 아무것도 그리지 않는다", () => {
    const { rerender } = renderWithProviders(<NtisInsights data={null} unavailable />);
    expect(screen.getByText(UNAVAILABLE_HINT)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    rerender(<NtisInsights data={{ notice: "n", projects: [], ntis_recommended: [] }} />);
    expect(screen.queryByText("NTIS 과제 성과·추천")).not.toBeInTheDocument();
  });
});

describe("유사과제 표의 national_rnd 티어", () => {
  it("tier_label 을 그대로 보이고, 비어 있으면 보충한다", () => {
    renderWithProviders(<AlertsTable alerts={[ntisAlert, { ...ntisAlert, doc_id: "ntis:2", tier_label: "" }]} />);
    expect(screen.getAllByText("국가R&D 과제")).toHaveLength(2);
    expect(tierLabel({ tier: "national_rnd", tier_label: "" })).toBe("국가R&D 과제");
    expect(tierLabel({ tier: "own", tier_label: "사내(철도연구원)" })).toBe("사내(철도연구원)");
    expect(tierLabel({ tier: "unknown_tier" })).toBe("unknown_tier");
  });
});

describe("② 화면의 NTIS 호출", () => {
  it("national_rnd 알림이 있으면 /v1/precheck/ntis-outcomes 를 같은 본문으로 1회 부르고 블록을 그린다", async () => {
    const { calls } = mockFetch({ "/v1/precheck/ntis-outcomes": fx, "/v1/precheck/comparison": problem(503, "꺼짐") });
    updateIdea({ precheck: { ...(precheckFx as PrecheckOut), alerts: [ntisAlert, ...(precheckFx as PrecheckOut).alerts] }, request: req });
    renderWithProviders(<Precheck />, { route: "/new/precheck" });
    expect(await screen.findByRole("heading", { name: "NTIS 추천" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { name: "주요 성과 (참고용)" })).toHaveLength(fx.projects.length);
    const ntisCalls = calls.filter((c) => c.url === "/v1/precheck/ntis-outcomes");
    expect(ntisCalls).toHaveLength(1);
    expect(ntisCalls[0]!.init?.method).toBe("POST");
    expect(JSON.parse(String(ntisCalls[0]!.init?.body))).toMatchObject({ goal: "d" });
    // 다음 단계 버튼은 NTIS 결과와 무관하게 열려 있다
    expect(screen.getByRole("button", { name: /다음: 선행연구 브리핑/ })).toBeEnabled();
  });

  it("503 이면 오류 배너 없이 한 줄 안내, NTIS 알림이 없으면 부르지 않는다", async () => {
    const { calls } = mockFetch({ "/v1/precheck/ntis-outcomes": problem(503, "키 없음"), "/v1/precheck/comparison": problem(503, "꺼짐") });
    updateIdea({ precheck: { ...(precheckFx as PrecheckOut), alerts: [ntisAlert] }, request: req });
    const r = renderWithProviders(<Precheck />, { route: "/new/precheck" });
    expect(await screen.findByText(UNAVAILABLE_HINT)).toBeInTheDocument();
    expect(screen.queryByText("키 없음")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /다음: 선행연구 브리핑/ })).toBeEnabled();
    r.unmount();
    resetIdea();
    updateIdea({ precheck: precheckFx as PrecheckOut, request: req });
    renderWithProviders(<Precheck />, { route: "/new/precheck" });
    expect(await screen.findByRole("heading", { name: /유사과제 1건/ })).toBeInTheDocument();
    expect(calls.filter((c) => c.url === "/v1/precheck/ntis-outcomes")).toHaveLength(1); // 앞 사례의 1회뿐
    expect(screen.queryByText(UNAVAILABLE_HINT)).not.toBeInTheDocument();
  });
});
