import { render, screen } from "@testing-library/react";
import { Eyebrow } from "./eyebrow";
import { ProgressBar } from "./progress-bar";
import { StatusChip } from "./status-chip";
import { Tabs } from "./tabs";
import { expectNoA11yViolations } from "@/test/utils";

describe("Research Studio 공용 조각", () => {
  it("상태 칩은 한국어 문구를 쓴다", () => {
    render(
      <div>
        <StatusChip status="writing" />
        <StatusChip status="reviewing" />
        <StatusChip status="done" />
        <StatusChip status="done">완료</StatusChip>
      </div>,
    );
    expect(screen.getByText("작성 중")).toHaveAttribute("data-status", "writing");
    expect(screen.getByText("검토 중")).toHaveAttribute("data-status", "reviewing");
    expect(screen.getByText("마무리 완료")).toHaveAttribute("data-status", "done");
    expect(screen.getByText("완료")).toBeInTheDocument();
  });

  it("진행률 막대는 0~100 으로 자르고 이름을 가진다", async () => {
    const { container } = render(
      <div>
        <ProgressBar value={42.4} label="첫 제안서 진행률" />
        <ProgressBar value={140} />
        <ProgressBar value={-3} showValue={false} />
      </div>,
    );
    const bars = screen.getAllByRole("progressbar");
    expect(bars[0]).toHaveAccessibleName("첫 제안서 진행률");
    expect(bars[0]).toHaveAttribute("aria-valuenow", "42");
    expect(bars[1]).toHaveAccessibleName("진행률");
    expect(bars[1]).toHaveAttribute("aria-valuenow", "100");
    expect(bars[2]).toHaveAttribute("aria-valuenow", "0");
    expect(screen.getByText("42%")).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("영어 라벨은 장식(화면 읽기 숨김)이고 한국어 제목과 함께 쓴다", async () => {
    const { container } = render(
      <section aria-labelledby="h">
        <Eyebrow>Overview</Eyebrow>
        <h2 id="h">연구 한눈에 보기</h2>
      </section>,
    );
    expect(screen.getByText("Overview")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByText("Overview")).toHaveClass("eyebrow");
    expect(screen.getByRole("heading", { name: "연구 한눈에 보기" })).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("탭 건수는 탭 이름에 붙는다", () => {
    render(
      <Tabs
        label="제안서 상태"
        value="all"
        onChange={() => undefined}
        items={[
          { id: "all", label: "전체", count: 4 },
          { id: "done", label: "완료" },
        ]}
      />,
    );
    expect(screen.getByRole("tab", { name: "전체 4" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "완료" })).toHaveAttribute("aria-selected", "false");
  });
});
