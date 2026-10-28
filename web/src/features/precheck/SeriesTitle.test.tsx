/** ② 같은 연작 한 줄 (레인 A, ADR 0043) — "○○(연작 n건)" + [펼치기]/[접기] 연도별 목록, 선택은 행 하나, 내부 번호 없음. */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations, renderWithProviders } from "@/test/utils";
import type { PrecheckAlert, SeriesView } from "@/api/types";
import { SimilarRowsTable } from "./SimilarRowsTable";
import { choiceOf, seriesSources } from "./model";

const INTERNAL_ID = /\b(own|alio|ntis|scienceon|openalex|korail_web|g2b):[\w-]+/;

const SERIES: SeriesView = {
  label: "광역철도 수송수요 예측",
  count: 3,
  display: "광역철도 수송수요 예측(연작 3건)",
  members: [
    {
      title: "2023년도 광역철도 수송수요 예측 연구",
      year: 2023,
      doc_id: "alio:sum-9a5d",
      source: "alio",
      source_label: "알리오 공시",
      url: null,
      summary: "2023년도 광역철도 수송수요를 예측함",
      refs: [{ doc_id: "alio:sum-9a5d", title: "2023년도 광역철도 수송수요 예측 연구", source: "alio", source_label: "알리오 공시", url: null }],
    },
    {
      title: "2024년도 광역철도 수송수요 예측 연구",
      year: 2024,
      doc_id: "own:7fcd",
      source: "own",
      source_label: "사내 과제 · 공사 홈페이지",
      url: "https://info.korail.com/x",
      summary: null,
      refs: [],
    },
    {
      title: "2025년도 광역철도 수송수요 예측 연구",
      year: 2025,
      doc_id: "alio:sum-2990",
      source: "alio",
      source_label: "알리오 공시",
      url: null,
      summary: null,
      refs: [],
    },
  ],
};

const alert = (over: Partial<PrecheckAlert>): PrecheckAlert => ({
  doc_id: "alio:sum-2990",
  title: "2025년도 광역철도 수송수요 예측 연구",
  tier: "own",
  similarity: 0.86,
  blocking: false,
  basis: "summary",
  keywords: ["광역철도"],
  status: null,
  own_detail: "institute",
  tier_label: "사내(철도연구원)",
  rerank_score: 0.9,
  relevance: "high",
  relevance_label: "높음",
  source_label: "알리오 공시 연구보고서",
  judgment: null,
  judged_by: null,
  merged_ids: ["alio:sum-9a5d", "own:7fcd"],
  series: SERIES,
  ...over,
});

const OTHER = alert({ doc_id: "own:nambu", title: "경기남부권 신설노선 개통에 따른 광역철도 수송수요 변화 예측", merged_ids: [], series: null, source_label: "사내 과제 현황" });

describe("② 같은 연작 한 줄", () => {
  it("연작 행 — 라벨(연작 n건)·자료원 모음, 펼치면 연도별 목록(제목 · 자료원), 접으면 숨김, 내부 번호 없음 (axe 0)", async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(<SimilarRowsTable alerts={[alert({}), OTHER]} choices={{}} onChoose={vi.fn()} />);
    const rows = screen.getAllByTestId("similar-row");
    expect(rows).toHaveLength(2);
    const row = rows[0]!;
    expect(within(row).getByText("광역철도 수송수요 예측(연작 3건)")).toBeInTheDocument();
    expect(within(row).getByText("알리오 공시 · 사내 과제 · 공사 홈페이지")).toBeInTheDocument();
    expect(within(row).queryByText(/같은 제목 \d+건 묶음/)).toBeNull();
    expect(within(row).queryByRole("list", { name: /연도별 목록/ })).toBeNull();

    await user.click(within(row).getByRole("button", { name: "펼치기" }));
    const list = within(row).getByRole("list", { name: "광역철도 수송수요 예측 연도별 목록" });
    const items = within(list).getAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual([
      expect.stringContaining("2023"),
      expect.stringContaining("2024"),
      expect.stringContaining("2025"),
    ]);
    expect(within(list).getByRole("button", { name: /2024년도 광역철도 수송수요 예측 연구 \(사내 과제 · 공사 홈페이지\) 근거 보기/ })).toBeInTheDocument();
    expect(container.textContent).not.toMatch(INTERNAL_ID);
    await expectNoA11yViolations(container);

    // 판 하나를 누르면 근거 패널(요약)
    await user.click(within(list).getByRole("button", { name: /2023년도 .* 근거 보기/ }));
    expect(await screen.findByText("2023년도 광역철도 수송수요를 예측함")).toBeInTheDocument();
    await user.keyboard("{Escape}");

    await user.click(within(row).getByRole("button", { name: "접기" }));
    expect(within(row).queryByRole("list", { name: /연도별 목록/ })).toBeNull();
    // 연작이 아닌 행은 종전 그대로
    expect(within(rows[1]!).getByText(OTHER.title)).toBeInTheDocument();
  });

  it("[유사함]/[관련 없음] 은 연작 행 하나 — 대표 doc_id 로 고르고, 구성원 선택도 행에 적용", async () => {
    const user = userEvent.setup();
    const onChoose = vi.fn();
    renderWithProviders(<SimilarRowsTable alerts={[alert({})]} choices={{}} onChoose={onChoose} />);
    const group = screen.getByRole("group", { name: "광역철도 수송수요 예측(연작 3건) 선택" });
    await user.click(within(group).getByRole("button", { name: "유사함" }));
    expect(onChoose).toHaveBeenCalledWith("alio:sum-2990", "similar");
    expect(choiceOf(alert({}), { "own:7fcd": "unrelated" })).toBe("unrelated");
    expect(seriesSources(SERIES)).toBe("알리오 공시 · 사내 과제 · 공사 홈페이지");
  });
});
