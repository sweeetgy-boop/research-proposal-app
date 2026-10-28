import { render, screen } from "@testing-library/react";
import { CharDiff, DiffView, pairRows } from "./DiffView";
import diffFixture from "@/test/fixtures/diff.json";
import type { DiffOut } from "@/api/types";

describe("DiffView", () => {
  it("같은 sentence_id 끼리 짝짓고 남는 것은 단독", () => {
    const pairs = pairRows(
      [{ sentence_id: "s:m:0", text: "a" }, { sentence_id: "s:m:2", text: "c" }],
      [{ sentence_id: "s:m:0", text: "a2" }, { sentence_id: "s:m:5", text: "e" }],
    );
    expect(pairs).toEqual([
      { before: { sentence_id: "s:m:0", text: "a" }, after: { sentence_id: "s:m:0", text: "a2" } },
      { before: { sentence_id: "s:m:2", text: "c" }, after: null },
      { before: null, after: { sentence_id: "s:m:5", text: "e" } },
    ]);
  });

  it("글자 단위 ins/del", () => {
    const { container } = render(<CharDiff before="검측 이력을 분석함." after="검측 이력을 정밀 분석함." />);
    expect(container.querySelector("ins")?.textContent).toBe("정밀 ");
    expect(container.querySelector("del")).toBeNull();
  });

  it("백엔드 diff 응답을 섹션별로 그린다", () => {
    const { container } = render(<DiffView diff={diffFixture as unknown as DiffOut} />);
    expect(screen.getByText(/v1 → v3/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /2-다 연구 방법/ })).toBeInTheDocument();
    expect(container.querySelectorAll("ins").length).toBeGreaterThan(0);
    expect(container.querySelectorAll("del").length).toBeGreaterThan(0);
    expect(container.textContent).toContain("직접");
  });

  it("차이가 없으면 안내", () => {
    render(<DiffView diff={{ run_id: "r", notice: "", from: 1, to: 2, sections: [] }} />);
    expect(screen.getByText(/본문이 같습니다/)).toBeInTheDocument();
  });

  it("[G] figures_changed 는 '그림 변경' 목록으로 — 종류·섹션·변경 라벨", () => {
    const figures_changed = [
      { figure_id: "fig-concept-1", kind: "concept", section: "objective", change: "texts" },
      { figure_id: "fig-roadmap-1", kind: "roadmap", section: "expected_technology", change: "excluded" },
      { figure_id: "fig-process-1", kind: "process", section: "method", change: "confirmed" },
    ];
    render(<DiffView diff={{ run_id: "r", notice: "", from: 4, to: 5, sections: [], figures_changed }} />);
    expect(screen.queryByText(/본문이 같습니다/)).toBeNull();
    expect(screen.getByRole("heading", { name: /그림 변경/ })).toBeInTheDocument();
    expect(screen.getByText("연구 개념도")).toBeInTheDocument();
    expect(screen.getByText("글자 수정")).toBeInTheDocument();
    expect(screen.getByText("성과지표·활용 로드맵")).toBeInTheDocument();
    expect(screen.getByText("뺌")).toBeInTheDocument();
    expect(screen.getByText("확인함")).toBeInTheDocument();
    expect(screen.getByText("3-나 기대효과 (기술혁신 측면)")).toBeInTheDocument();
  });

  it("[G] 본문·그림이 함께 바뀌면 둘 다 그린다", () => {
    const diff = { ...(diffFixture as unknown as DiffOut), figures_changed: [{ figure_id: "fig-concept-1", kind: "concept", section: "objective", change: "redrawn" }] };
    render(<DiffView diff={diff} />);
    expect(screen.getByText(/그림 변경 1건/)).toBeInTheDocument();
    expect(screen.getByText("다시 그림")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /2-다 연구 방법/ })).toBeInTheDocument();
  });
});
