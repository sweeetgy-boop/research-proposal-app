import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations, renderWithProviders } from "@/test/utils";
import { BriefView } from "./BriefView";
import briefFx from "@/test/fixtures/brief.json";
import type { BriefOut } from "@/api/types";

const brief = briefFx as BriefOut;

describe("선행연구 브리핑", () => {
  it("항목·요약 없음·연도 막대·주제어·공백 후보, 체크 → onToggle, axe 통과", async () => {
    const onToggle = vi.fn();
    const { container } = renderWithProviders(<BriefView brief={brief} selected={["alio:fake-1#0"]} onToggle={onToggle} />);
    expect(screen.getByRole("heading", { name: "선행연구 2건" })).toBeInTheDocument();
    expect(screen.getByText("궤도 상태 감지와 열화 추정을 다룸.")).toBeInTheDocument();
    expect(screen.getByText("요약 없음")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "연도별 건수" })).toHaveTextContent("2024");
    expect(screen.getByRole("list", { name: "주제어" }).children).toHaveLength(5);
    expect(screen.getByText("후보")).toBeInTheDocument();
    expect(screen.getByText("재래선 구간의 열화 진행 속도 자료가 없음.")).toBeInTheDocument();
    const boxes = screen.getAllByRole("checkbox");
    expect(boxes[0]).toBeChecked();
    expect(boxes[1]).not.toBeChecked();
    await userEvent.click(boxes[1]!);
    expect(onToggle).toHaveBeenCalledWith("openalex:fake-1#0", true);
    await expectNoA11yViolations(container);
  });
});
