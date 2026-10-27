import { screen } from "@testing-library/react";
import { expectNoA11yViolations, renderWithProviders } from "@/test/utils";
import { ComparisonTable, TITLE_ONLY } from "./ComparisonTable";
import comparisonFx from "@/test/fixtures/comparison.json";
import type { ComparisonOut } from "@/api/types";

const data = (comparisonFx as ComparisonOut).comparison;

describe("차별성 비교표", () => {
  it("제안 과제 + 유사과제 행, 5 관점 열, 제목만인 과제는 '정보 없음(제목 기준)', 추천 카드 링크, axe 통과", async () => {
    const { container } = renderWithProviders(<ComparisonTable data={data} recommendationFor={new Map([["alio:fake-1", 0]])} />);
    const table = screen.getByRole("table", { name: /차별성 비교표/ });
    expect(table).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader")).toHaveLength(6);
    expect(screen.getAllByRole("rowheader")).toHaveLength(3);
    expect(screen.getByText("제안 과제")).toBeInTheDocument();
    expect(screen.getAllByText(TITLE_ONLY)).toHaveLength(5);
    expect(screen.getByRole("link", { name: "추천 1번 카드 보기" })).toHaveAttribute("href", "#rec-0");
    expect(screen.getByText("검측 이력 기반 보수 우선순위 산정")).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("503 이면 꺼짐 안내, 로딩이면 aria-busy", () => {
    const { rerender } = renderWithProviders(<ComparisonTable data={null} unavailable />);
    expect(screen.getByText(/비교표가 꺼져 있습니다/)).toBeInTheDocument();
    rerender(<ComparisonTable data={null} loading />);
    expect(document.querySelector("[aria-busy='true']")).not.toBeNull();
  });
});
