/** 비슷한 자료 묶음 + 비교 분석 (계약 problem-card.md 4.6절) — 접힘·뒤에서 채워지는 표·'추정' 배지·[원문 보기]·
 *  분석이 안 되면 묶음만·묶음이 없으면 호출 0·상한. 응답 모양은 api/types-novel.ts 그대로(백엔드 없음). */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations, mockFetch, problem, renderWithProviders } from "@/test/utils";
import { ANALOGY_GROUP_PATH, NEEDS_SOURCE_TEXT } from "@/api/analogyGroups";
import type { Analogy, AnalogyGroupAnalysis, AnalogyReport } from "@/api/types-novel";
import type { PrecheckRequest } from "@/api/types-precheck";
import { emptyRequest } from "@/lib/validation";
import { AnalogyList } from "./NovelPlans";

afterEach(() => vi.unstubAllGlobals());

const INTERNAL = /\b(own|alio|ntis|scienceon|openalex|kipris_kr):[\w-]+|doc_id|needs_source|use_basis|group_id|\brun\b/i;
const REQ: PrecheckRequest = { ...emptyRequest(), title_hint: "역사 화장실 악취 저감", current_state: "악취 민원", root_cause: "역류", limitation: "환기 한계", goal: "악취 저감" };

const lead = (over: Partial<Analogy> = {}): Analogy => ({
  doc_id: "kipris_kr:1020190001",
  title: "악취 역류 차단 장치",
  source: "kipris_kr",
  source_label: "KIPRIS 특허",
  domain_label: "위생 설비",
  why_relevant: "악취 역류라는 같은 문제를 다룸",
  url: "https://example.org/p1",
  year: 2019,
  live: false,
  similar: [
    { doc_id: "kipris_kr:1020000002", title: "하수구 악취 역류 방지기", source: "kipris_kr", source_label: "KIPRIS 특허", url: "https://example.org/p2", year: 2000 },
    { doc_id: "kipris_kr:1020090003", title: "악취 역류 방지장치", source: "kipris_kr", source_label: "KIPRIS 특허", url: "javascript:alert(1)", year: 2009 },
  ],
  group_id: "a1b2c3d4",
  ...over,
});
const single: Analogy = { doc_id: "scienceon:X1", title: "공중화장실 복합악취 저감", source: "scienceon", source_label: "ScienceON", domain_label: "환경", why_relevant: "악취", url: null, year: 2021, live: false, similar: [], group_id: null };

const OK: AnalogyGroupAnalysis = {
  status: "ok",
  group_id: "a1b2c3d4",
  items: [
    { doc_id: "kipris_kr:1020190001", title: "악취 역류 차단 장치", source_label: "KIPRIS 특허", url: "https://example.org/p1", year: 2019, core_method: "배수 유닛 안에 수막을 만든다", difference: "싱크 배수용", use: "화장실 배수구에 수막 방식 검토", use_basis: "추정", limit: NEEDS_SOURCE_TEXT, needs_source: true },
    { doc_id: "kipris_kr:1020000002", title: "하수구 악취 역류 방지기", source_label: "KIPRIS 특허", url: "https://example.org/p2", year: 2000, core_method: "판 높이차로 물막이", difference: "바닥 하수구용", use: "바닥 배수구 적용 검토", use_basis: "추정", limit: "물이 마르면 효과 없음", needs_source: false },
    { doc_id: "kipris_kr:1020090003", title: "악취 역류 방지장치", source_label: "KIPRIS 특허", url: null, year: 2009, core_method: NEEDS_SOURCE_TEXT, difference: NEEDS_SOURCE_TEXT, use: NEEDS_SOURCE_TEXT, use_basis: "추정", limit: NEEDS_SOURCE_TEXT, needs_source: true },
  ],
  summary: { common: "물이나 판으로 배관을 막아 역류를 차단", gap: "환기와 함께 쓰는 방식" },
  cached: false,
  seconds: 12.3,
  reason_label: null,
};

const analyzeCalls = (calls: { url: string; init?: RequestInit }[]) => calls.filter((c) => c.url.startsWith(ANALOGY_GROUP_PATH));

describe("비슷한 자료 묶음", () => {
  it("대표 아래 접힘 버튼 — 펼치면 구성원 제목 링크·자료원·연도, http(s) 아닌 주소는 링크로 만들지 않음 (axe 0, 내부 번호 없음)", async () => {
    mockFetch({ [ANALOGY_GROUP_PATH]: { ...OK, status: "off", items: [], summary: null } });
    const { container } = renderWithProviders(<AnalogyList items={[lead(), single]} analysisRequest={REQ} />);
    expect(screen.getAllByTestId("novel-analogy")).toHaveLength(2);
    const toggle = screen.getByTestId("analogy-similar-toggle");
    expect(toggle).toHaveTextContent("비슷한 자료 2건 더 보기");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByTestId("analogy-similar-list")).not.toBeVisible();
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const list = screen.getByTestId("analogy-similar-list");
    expect(list).toBeVisible();
    expect(within(list).getByRole("link", { name: /하수구 악취 역류 방지기/ })).toHaveAttribute("href", "https://example.org/p2");
    expect(within(list).getByText(/KIPRIS 특허 · 2000/)).toBeInTheDocument();
    expect(within(list).queryByRole("link", { name: /악취 역류 방지장치/ })).toBeNull();
    expect(within(list).getByText("악취 역류 방지장치")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(INTERNAL);
    await expectNoA11yViolations(container);
  });

  it("뒤에서 분석 — 기다리는 동안 한 줄, 오면 비교 표(머리 5칸·행 = 자료)·'추정' 배지·요약 두 줄·[원문 보기] (axe 0)", async () => {
    let release: (v: unknown) => void = () => undefined;
    const gate = new Promise((r) => (release = r));
    const { calls } = mockFetch({});
    // mockFetch 는 함수 결과를 그대로 JSON 으로 만든다 → 지연은 fetch 자체를 감싼다
    const inner = globalThis.fetch;
    vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (!url.startsWith(ANALOGY_GROUP_PATH)) return inner(input, init);
      calls.push({ url, init });
      await gate;
      return new Response(JSON.stringify(OK), { status: 200, headers: { "content-type": "application/json" } });
    });
    const { container, rerender } = renderWithProviders(<AnalogyList items={[lead(), single]} analysisRequest={REQ} />);
    expect(await screen.findByTestId("analogy-group-waiting")).toHaveTextContent("비교 분석 중…");
    expect(screen.queryByTestId("analogy-group-table")).toBeNull();
    // 요청 몸통 — 과제 입력 + 대표·구성원 문서
    const body = JSON.parse(String(analyzeCalls(calls)[0]?.init?.body)) as { request: PrecheckRequest; doc_ids: string[] };
    expect(body.doc_ids).toEqual(["kipris_kr:1020190001", "kipris_kr:1020000002", "kipris_kr:1020090003"]);
    expect(body.request.goal).toBe("악취 저감");
    release(null);
    const table = await screen.findByTestId("analogy-group-table");
    expect(screen.queryByTestId("analogy-group-waiting")).toBeNull();
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["자료", "핵심 방식", "다른 점", "이 과제에 활용할 점", "한계"]);
    const rows = within(table).getAllByTestId("analogy-group-row") as [HTMLElement, HTMLElement, HTMLElement];
    expect(rows).toHaveLength(3);
    expect(within(rows[0]).getByRole("rowheader")).toHaveTextContent("악취 역류 차단 장치");
    expect(within(rows[0]).getByText("배수 유닛 안에 수막을 만든다")).toBeInTheDocument();
    expect(within(table).getAllByTestId("analogy-group-basis").map((b) => b.textContent)).toEqual(["추정", "추정", "추정"]);
    // [원문 보기] — 구분 안 된 칸에만, 주소가 있을 때만
    const links0 = within(rows[0]).getAllByTestId("analogy-group-source-link");
    expect(links0).toHaveLength(1);
    expect(links0[0]!).toHaveAttribute("href", "https://example.org/p1");
    expect(links0[0]!).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(rows[1]).queryByTestId("analogy-group-source-link")).toBeNull();
    expect(within(rows[2]).queryByTestId("analogy-group-source-link")).toBeNull();
    expect(within(rows[2]).getAllByText(NEEDS_SOURCE_TEXT)).toHaveLength(4);
    const summary = screen.getByTestId("analogy-group-summary");
    expect(summary).toHaveTextContent("공통 접근 — 물이나 판으로 배관을 막아 역류를 차단");
    expect(summary).toHaveTextContent("아직 다뤄지지 않은 부분 — 환기와 함께 쓰는 방식");
    expect(container.textContent).not.toMatch(INTERNAL);
    await expectNoA11yViolations(container);
    // 다시 그려져도(가제 칸 수정 등) 같은 묶음을 다시 부르지 않는다
    rerender(<AnalogyList items={[lead(), single]} analysisRequest={{ ...REQ, title_hint: "바꾼 가제" }} />);
    await screen.findByTestId("analogy-group-table");
    expect(analyzeCalls(calls)).toHaveLength(1);
  });

  for (const [name, route] of [
    ["실패", { ...OK, status: "failed", items: [], summary: null, reason_label: "AI 응답을 받지 못했습니다" }],
    ["건너뜀", { ...OK, status: "skipped", items: [], summary: null }],
    ["꺼짐", { ...OK, status: "off", items: [], summary: null }],
    ["서버 오류", () => problem(500, "오류")],
  ] as const) {
    it(`분석이 ${name} 이면 묶음만 — 표·요약·알림 없음`, async () => {
      const { calls } = mockFetch({ [ANALOGY_GROUP_PATH]: route });
      renderWithProviders(<AnalogyList items={[lead()]} analysisRequest={REQ} />);
      await waitFor(() => expect(analyzeCalls(calls)).toHaveLength(1));
      await waitFor(() => expect(screen.queryByTestId("analogy-group-waiting")).toBeNull());
      expect(screen.getByTestId("analogy-similar-toggle")).toBeInTheDocument();
      expect(screen.queryByTestId("analogy-group-table")).toBeNull();
      expect(screen.queryByTestId("analogy-group-summary")).toBeNull();
      expect(screen.queryByRole("alert")).toBeNull();
      expect(screen.queryByText(/AI 응답을 받지 못했습니다/)).toBeNull();
    });
  }

  it("묶음이 없으면 종전 화면 그대로 — 버튼·표 없음, 분석 호출 0", async () => {
    const { calls } = mockFetch({ [ANALOGY_GROUP_PATH]: OK });
    const plain = { ...lead(), similar: undefined, group_id: undefined };
    renderWithProviders(<AnalogyList items={[plain, single]} analysisRequest={REQ} />);
    expect(screen.getAllByTestId("novel-analogy")).toHaveLength(2);
    expect(screen.queryByTestId("analogy-group")).toBeNull();
    expect(screen.queryByTestId("analogy-similar-toggle")).toBeNull();
    await new Promise((r) => setTimeout(r, 30));
    expect(calls).toHaveLength(0);
  });

  it("분석은 상한까지만 — 기본 2묶음, 서버가 0 을 주면 부르지 않는다. 입력이 없어도 부르지 않는다", async () => {
    const groups = [1, 2, 3].map((n) =>
      lead({ doc_id: `kipris_kr:A${n}`, title: `자료 ${n}`, group_id: `g${n}`, similar: [{ doc_id: `kipris_kr:B${n}`, title: `비슷한 자료 ${n}`, source: "kipris_kr", source_label: "KIPRIS 특허", url: null, year: null }] }),
    );
    const first = mockFetch({ [ANALOGY_GROUP_PATH]: { ...OK, status: "failed", items: [], summary: null } });
    const a = renderWithProviders(<AnalogyList items={groups} analysisRequest={REQ} />);
    expect(screen.getAllByTestId("analogy-similar-toggle")).toHaveLength(3);
    await waitFor(() => expect(analyzeCalls(first.calls)).toHaveLength(2));
    await new Promise((r) => setTimeout(r, 30));
    expect(analyzeCalls(first.calls)).toHaveLength(2);
    expect(analyzeCalls(first.calls).map((c) => (JSON.parse(String(c.init?.body)) as { doc_ids: string[] }).doc_ids[0])).toEqual(["kipris_kr:A1", "kipris_kr:A2"]);
    a.unmount();

    const off = mockFetch({ [ANALOGY_GROUP_PATH]: OK });
    const report = { kind: "other_field", heading: "다른 분야 사례", description: "", count: 3, dropped_weak: 0, sources_total: 0, sources_checked: 0, checked_labels: [], unavailable: [], partial: false, languages: [], scope_text: "", empty_text: "", group_analyze_max: 0 } as AnalogyReport;
    const b = renderWithProviders(<AnalogyList items={groups} report={report} analysisRequest={REQ} />);
    expect(screen.getAllByTestId("analogy-similar-toggle")).toHaveLength(3);
    await new Promise((r) => setTimeout(r, 30));
    expect(off.calls).toHaveLength(0);
    b.unmount();

    renderWithProviders(<AnalogyList items={groups} />);
    await new Promise((r) => setTimeout(r, 30));
    expect(off.calls).toHaveLength(0);
  });
});
