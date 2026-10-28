/** [11] 분석 기법 추천 카드 — 추천 배지·이유·[넣기 확정]·[필요 없음]·[다른 기법으로 바꾸기] POST 본문,
 *  항목 출처, 접힌 "필요 없다고 한 추천"·[다시 넣기], 추천 결과(해당 없음)·[다시 시도], 조회 화면, axe. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FigureCard } from "./FigureCard";
import { FigureList } from "./FigureList";
import { TechniqueStatus } from "./TechniqueCard";
import { expectNoA11yViolations, mockFetch, renderWithProviders } from "@/test/utils";
import draftFx from "@/test/fixtures/draft.json";
import version1 from "@/test/fixtures/version1.json";
import type { DraftOut, FigureV2, FiguresOutV2 } from "@/api/types";

afterEach(() => vi.unstubAllGlobals());

const draft = draftFx as unknown as DraftOut;
const id = draft.run_id;
const base = draft.figures![0]!;
const swot: FigureV2 = {
  ...base,
  id: "f:tech_importance:t1",
  kind: "technique",
  label: "SWOT 분석",
  section: "tech_importance",
  caption: "SWOT 분석",
  technique: "swot",
  family_label: "정성 분석",
  prelim_note: "제안 내용 기반 예비 평가",
  provenance: [
    { group: "강점", text: "검측 이력 자료", rating: "상", amount: "", source_kind: "sentence", section: "method", sentence_no: 1, source_label: "본문 문장 1" },
    { group: "약점", text: "다짐 효과", rating: "중", amount: "", source_kind: "input", section: null, sentence_no: null, source_label: "제안 입력: 발생 원인" },
  ],
  recommendation: {
    technique: "swot",
    technique_label: "SWOT 분석",
    reason: "공사 검측 자료와 선행연구 공백이 함께 있음",
    status: "pending",
    status_label: "결정 전",
    swapped_from: null,
    swapped_from_label: null,
    model: "gemini-4-argon",
  },
};
const url = `/v1/runs/${id}/figures/${encodeURIComponent(swot.id)}`;
const saved = { run_id: id, status: "editing", ...version1, version: 3 };
const listOut: FiguresOutV2 = {
  run_id: id,
  version: 2,
  figures: [swot],
  techniques: {
    status: "none",
    status_label: "해당 없음",
    message: "해당 없음 — 비교할 대안이 본문에 없음",
    picks: [],
    dropped: [],
    model: "gemini-4-argon",
    at: null,
    can_retry: true,
  },
  technique_catalog: [
    { key: "swot", label: "SWOT 분석", family: "qualitative", family_label: "정성 분석", section: "tech_importance", summary: "s", fits: "f" },
    { key: "pugh", label: "퓨 매트릭스(Pugh)", family: "evaluation", family_label: "비교·평가", section: "method", summary: "s", fits: "현행 방식과 제안 방식을 견줄 때" },
  ],
};

const bodies = (calls: { url: string; init?: RequestInit }[], u: string) =>
  calls.filter((c) => c.url === u && c.init?.method === "POST").map((c) => JSON.parse(String(c.init?.body)) as Record<string, unknown>);

function mount(figure: FigureV2, opts: { readOnly?: boolean } = {}) {
  const onApplied = vi.fn();
  const r = renderWithProviders(<FigureCard runId={id} figure={figure} baseVersion={2} onApplied={onApplied} {...opts} />);
  return { ...r, onApplied };
}

describe("분석 기법 추천 카드", () => {
  it("추천 배지·이유·예비 평가·항목 출처·버튼, [빼기] 대신 [필요 없음], axe 통과", async () => {
    mockFetch({});
    const { container } = mount(swot);
    const panel = screen.getByRole("region", { name: "추천 — SWOT 분석" });
    expect(within(panel).getByText("결정 전")).toBeInTheDocument();
    expect(within(panel).getByText("공사 검측 자료와 선행연구 공백이 함께 있음")).toBeInTheDocument();
    expect(within(panel).getByText(/결정하지 않고 마무리하면 제안서에 들어갑니다/)).toBeInTheDocument();
    expect(screen.getByText(/제안 내용 기반 예비 평가/)).toBeInTheDocument();
    await userEvent.click(screen.getByText("항목 출처 2개"));
    expect(screen.getByText(/2-다 연구 방법 및 주요내용 문장 1/)).toBeInTheDocument();
    expect(screen.getByText(/제안 입력: 발생 원인/)).toBeInTheDocument();
    for (const name of ["SWOT 분석 넣기 확정", "SWOT 분석 필요 없음", "SWOT 분석 다른 기법으로 바꾸기"]) expect(screen.getByRole("button", { name })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "SWOT 분석 빼기" })).toBeNull();
    expect(container.textContent).not.toMatch(/s:method|input:root/); // 내부 id 를 보이지 않는다
    await expectNoA11yViolations(container);
  });

  it("[넣기 확정]·[필요 없음] → action POST, 저장 뒤 onApplied", async () => {
    const { calls } = mockFetch({ [url]: saved });
    const { onApplied } = mount(swot);
    await userEvent.click(screen.getByRole("button", { name: "SWOT 분석 넣기 확정" }));
    await waitFor(() => expect(onApplied).toHaveBeenCalledWith(3));
    await userEvent.click(screen.getByRole("button", { name: "SWOT 분석 필요 없음" }));
    await waitFor(() => expect(bodies(calls, url)).toHaveLength(2));
    expect(bodies(calls, url)).toEqual([
      { action: "accept", base_version: 2 },
      { action: "dismiss", base_version: 2 },
    ]);
  });

  it("[다른 기법으로 바꾸기] — 목록(현재 기법 제외)에서 골라 swap POST, axe 통과", async () => {
    const { calls } = mockFetch({ [`/v1/runs/${id}/figures`]: listOut, [url]: saved });
    const { onApplied } = mount(swot);
    await userEvent.click(screen.getByRole("button", { name: "SWOT 분석 다른 기법으로 바꾸기" }));
    const dialog = await screen.findByRole("dialog");
    const radio = await within(dialog).findByRole("radio", { name: /퓨 매트릭스/ });
    expect(within(dialog).queryByRole("radio", { name: /SWOT/ })).toBeNull();
    expect(within(dialog).getByRole("button", { name: "바꾸기" })).toBeDisabled();
    await userEvent.click(radio);
    await expectNoA11yViolations(dialog);
    await userEvent.click(within(dialog).getByRole("button", { name: "바꾸기" }));
    await waitFor(() => expect(onApplied).toHaveBeenCalledWith(3));
    expect(bodies(calls, url)).toEqual([{ action: "swap", technique: "pugh", base_version: 2 }]);
  });

  it("조회 화면은 배지·이유만 (버튼 없음)", () => {
    mockFetch({});
    mount(swot, { readOnly: true });
    expect(screen.getByRole("region", { name: "추천 — SWOT 분석" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /넣기 확정|필요 없음|다른 기법/ })).toBeNull();
  });

  it("필요 없다고 한 추천은 섹션 아래에 접히고 [다시 넣기] → restore", async () => {
    const dismissed: FigureV2 = { ...swot, included: false, recommendation: { ...swot.recommendation!, status: "dismissed", status_label: "필요 없음" } };
    const { calls } = mockFetch({ [url]: saved });
    const onApplied = vi.fn();
    const { container } = renderWithProviders(<FigureList runId={id} figures={[dismissed]} section="tech_importance" baseVersion={2} onApplied={onApplied} />);
    expect(screen.queryByRole("group", { name: "SWOT 분석" })).toBeNull(); // 카드는 접힌다
    await userEvent.click(screen.getByText("필요 없다고 한 추천 그림 1장"));
    await userEvent.click(screen.getByRole("button", { name: "SWOT 분석 다시 넣기" }));
    await waitFor(() => expect(onApplied).toHaveBeenCalledWith(3));
    expect(bodies(calls, url)).toEqual([{ action: "restore", base_version: 2 }]);
    await expectNoA11yViolations(container);
  });
});

describe("분석 기법 추천 결과", () => {
  it("해당 없음 사유 + [다시 시도] → POST techniques, 새 그림이 없으면 안내", async () => {
    const retryUrl = `/v1/runs/${id}/figures/techniques`;
    const { calls } = mockFetch({
      [`/v1/runs/${id}/figures`]: listOut,
      [retryUrl]: { run_id: id, status: "editing", created: false, techniques: { ...listOut.techniques!, status: "failed", status_label: "호출 실패", message: "호출 실패 — 모델이 답하지 않았습니다." } },
    });
    const onApplied = vi.fn();
    const { container } = renderWithProviders(<TechniqueStatus runId={id} baseVersion={2} onApplied={onApplied} />);
    expect(await screen.findByText("분석 기법 추천: 해당 없음")).toBeInTheDocument();
    expect(screen.getByText("해당 없음 — 비교할 대안이 본문에 없음")).toBeInTheDocument();
    await expectNoA11yViolations(container);
    await userEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    expect(await screen.findByText("분석 기법 추천: 호출 실패")).toBeInTheDocument();
    expect(screen.getByText("새 추천 그림은 없습니다.")).toBeInTheDocument();
    expect(bodies(calls, retryUrl)).toEqual([{ base_version: 2 }]);
    expect(onApplied).not.toHaveBeenCalled();
  });

  it("추천했으면 결과 한 줄만, [다시 시도] 없음", async () => {
    mockFetch({ [`/v1/runs/${id}/figures`]: { ...listOut, techniques: { ...listOut.techniques!, status: "recommended", status_label: "추천함", message: "분석 기법 1개를 추천했습니다" } } });
    renderWithProviders(<TechniqueStatus runId={id} baseVersion={2} onApplied={vi.fn()} />);
    expect(await screen.findByText("분석 기법 추천: 추천함")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다시 시도" })).toBeNull();
  });
});
