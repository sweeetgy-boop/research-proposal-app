/** ADR 0045 — ③ 생성 중 다 쓴 섹션 먼저 보기: 끝난 섹션 글(읽기 전용)·"작성 중" 섹션, 생성이 끝나면 숨김. */
import { screen } from "@testing-library/react";
import { SectionsSoFar } from "./SectionsSoFar";
import { expectNoA11yViolations, mockFetch, renderWithProviders } from "@/test/utils";

afterEach(() => vi.unstubAllGlobals());

const id = "20261029010101-abcdef01";

describe("SectionsSoFar", () => {
  it("다 쓴 섹션은 글, 남은 섹션은 '작성 중' (axe)", async () => {
    mockFetch({
      [`/v1/runs/${id}/sections-progress`]: {
        run_id: id,
        notice: "비신뢰",
        status: "running",
        sections: [{ key: "objective", sentences: ["검측 이력으로 진행 속도를 추정함."] }],
        pending: ["method"],
      },
    });
    const r = renderWithProviders(<SectionsSoFar runId={id} generating />);
    expect(await screen.findByText("검측 이력으로 진행 속도를 추정함.")).toBeInTheDocument();
    expect(screen.getByText("2-나 연구목적")).toBeInTheDocument();
    expect(screen.getByText("작성 중")).toBeInTheDocument();
    expect(screen.getByText(/다 쓴 섹션 1개 · 작성 중 1개/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull(); // 읽기 전용
    await expectNoA11yViolations(r.container);
  });

  it("생성이 끝나면 아무것도 그리지 않는다", () => {
    const { calls } = mockFetch({});
    renderWithProviders(<SectionsSoFar runId={id} generating={false} />);
    expect(screen.queryByText(/먼저 보기/)).toBeNull();
    expect(calls).toHaveLength(0);
  });
});
