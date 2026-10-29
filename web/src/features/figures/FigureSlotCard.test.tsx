/** ADR 0045 — 그림 자리 카드: 그리는 중 "그림 준비 중" → 그림 도착하면 그림 카드, 실패면 사유 + [다시 그리기]
 *  (POST /figures 본문 kind·section), 분석 기법 자리는 [다시 추천], 그림 작업 한 줄(준비 n장). */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FigureList } from "./FigureList";
import { FigureJobBanner } from "./FigureJobBanner";
import { FigureSlotCard } from "./FigureSlotCard";
import { figureJobSignature, figuresDrawing, slotsFor } from "./figureJob";
import { canFinalize } from "@/lib/runSteps";
import { expectNoA11yViolations, mockFetch, renderWithProviders } from "@/test/utils";
import draftFx from "@/test/fixtures/draft.json";
import runDrafted from "@/test/fixtures/run_drafted.json";
import version1 from "@/test/fixtures/version1.json";
import type { DraftOut, FigureSlot, RunState } from "@/api/types";

afterEach(() => vi.unstubAllGlobals());

const draft = draftFx as unknown as DraftOut;
const id = draft.run_id;
const concept = draft.figures![0]!; // section objective
const drawingSlot: FigureSlot = {
  slot_id: "slot-1",
  kind: "concept",
  section: "objective",
  display_name: "연구 개념도",
  status: "drawing",
  reason_label: null,
};
const failedSlot: FigureSlot = {
  ...drawingSlot,
  status: "failed",
  reason_label: "서버가 다시 시작되어 그리지 못했습니다 (호출 실패).",
};

function run(extra: Partial<RunState> & Record<string, unknown> = {}): RunState {
  return { ...(runDrafted as unknown as RunState), run_id: id, status: "drafted", ...extra } as RunState;
}

describe("FigureSlotCard·FigureList 자리", () => {
  it("그리는 중이면 그림 카드 자리에 '그림 준비 중', 도착하면 같은 섹션에 그림 카드 (axe)", async () => {
    mockFetch({});
    const onApplied = vi.fn();
    const r = renderWithProviders(
      <FigureList runId={id} figures={[]} section="objective" baseVersion={1} onApplied={onApplied} slots={[drawingSlot]} />,
    );
    const card = screen.getByRole("group", { name: "연구 개념도" });
    expect(card).toHaveAttribute("data-status", "drawing");
    expect(screen.getByText("그림 준비 중")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /다시 그리기/ })).toBeNull();
    await expectNoA11yViolations(r.container);
    // 그림이 도착 → 자리는 사라지고 그림 카드
    r.rerender(<FigureList runId={id} figures={[concept]} section="objective" baseVersion={1} onApplied={onApplied} slots={[]} />);
    expect(screen.queryByText("그림 준비 중")).toBeNull();
    expect(screen.getByTestId("figure-image")).toBeInTheDocument();
  });

  it("실패한 자리는 사유와 [다시 그리기] — 같은 종류·섹션으로 그림 추가를 부른다", async () => {
    const { calls } = mockFetch({ [`/v1/runs/${id}/figures`]: { run_id: id, status: "editing", ...version1, version: 3 } });
    const onApplied = vi.fn();
    renderWithProviders(<FigureSlotCard runId={id} slot={failedSlot} baseVersion={2} onApplied={onApplied} />);
    expect(screen.getByText(/서버가 다시 시작되어/)).toBeInTheDocument();
    expect(screen.getByText("그리지 못함")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "연구 개념도 다시 그리기" }));
    await waitFor(() => expect(onApplied).toHaveBeenCalledWith(3));
    const post = calls.find((c) => c.url === `/v1/runs/${id}/figures` && c.init?.method === "POST");
    expect(JSON.parse(String(post?.init?.body))).toEqual({ kind: "concept", section: "objective", base_version: 2 });
  });

  it("분석 기법 추천 자리(섹션 모름)는 그림 작업 한 줄 안에, 실패면 [다시 추천]", async () => {
    const { calls } = mockFetch({ [`/v1/runs/${id}/figures/techniques`]: { run_id: id, status: "none", created: false } });
    const tech: FigureSlot = { slot_id: "slot-2", kind: "technique", section: "", display_name: "분석 기법 추천 그림", status: "failed", reason_label: "그림을 그리지 못했습니다 (호출 실패)." };
    renderWithProviders(<FigureJobBanner run={run({ figures_status: "done", figure_slots: [tech] })} ready={1} baseVersion={1} onApplied={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "분석 기법 추천 그림 다시 추천" }));
    await waitFor(() => expect(calls.some((c) => c.url === `/v1/runs/${id}/figures/techniques` && c.init?.method === "POST")).toBe(true));
  });

  it("그리는 동안 한 줄 안내(준비 n장)·최종 마무리 막음, 끝나면 안내 없음", () => {
    mockFetch({});
    const drawing = run({ figures_status: "drawing", figure_slots: [drawingSlot] });
    const { rerender } = renderWithProviders(<FigureJobBanner run={drawing} ready={2} baseVersion={1} onApplied={vi.fn()} />);
    expect(screen.getByText("그림 준비 중")).toBeInTheDocument();
    expect(screen.getByText(/2장 준비됨 · 1장 그리는 중/)).toBeInTheDocument();
    expect(figuresDrawing(drawing)).toBe(true);
    expect(canFinalize({ ...drawing, flow: { ...drawing.flow, draft_review_skipped: "no_review_llm" } } as RunState).reason).toMatch(/그림 준비 중/);
    expect(slotsFor(drawing, "objective")).toHaveLength(1);
    const done = run({ figures_status: "done", figure_slots: [] });
    expect(figureJobSignature(done)).not.toBe(figureJobSignature(drawing));
    rerender(<FigureJobBanner run={done} ready={3} baseVersion={1} onApplied={vi.fn()} />);
    expect(screen.queryByTestId("figure-job")).toBeNull();
  });
});
