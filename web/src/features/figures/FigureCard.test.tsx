/** [G] 그림 카드 — 배지·안내·버튼, 글자 고치기/말로 고치기/확인함 → POST 본문, 409 표시, axe. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FigureCard } from "./FigureCard";
import { FigureList } from "./FigureList";
import { expectNoA11yViolations, mockFetch, problem, renderWithProviders } from "@/test/utils";
import draftFx from "@/test/fixtures/draft.json";
import version1 from "@/test/fixtures/version1.json";
import type { DraftOut, Figure } from "@/api/types";

afterEach(() => vi.unstubAllGlobals());

const draft = draftFx as unknown as DraftOut;
const id = draft.run_id;
const concept = draft.figures![0]!;
const process = draft.figures![1]!;
const url = `/v1/runs/${id}/figures/${concept.id}`;
const saved = { run_id: id, status: "editing", ...version1, version: 3 };

function mount(figure: Figure, opts: { disabled?: boolean; readOnly?: boolean } = {}) {
  const onApplied = vi.fn();
  const r = renderWithProviders(<FigureCard runId={id} figure={figure} baseVersion={draft.version} onApplied={onApplied} {...opts} />);
  return { ...r, onApplied };
}

const postBody = (calls: { url: string; init?: RequestInit }[]) => {
  const post = calls.find((c) => c.url === url && c.init?.method === "POST");
  expect(post).toBeDefined();
  return JSON.parse(String(post?.init?.body)) as Record<string, unknown>;
};

describe("FigureCard", () => {
  it("이미지·캡션·배지·안내·버튼을 그린다 (Nano Banana, 확인 전), axe 통과", async () => {
    mockFetch({});
    const { container } = mount(concept);
    const img = screen.getByRole("img", { name: concept.alt });
    expect(img).toHaveAttribute("src", expect.stringContaining(`${concept.image_url}?v=`));
    expect(screen.getByText(concept.caption)).toBeInTheDocument();
    expect(screen.getByText("Nano Banana Pro")).toBeInTheDocument();
    expect(screen.getByText("확인 전")).toBeInTheDocument();
    expect(screen.queryByText("뺌")).toBeNull();
    expect(screen.getByText(/AI 가 그린 그림입니다/)).toBeInTheDocument();
    for (const name of ["연구 개념도 확인함", "연구 개념도 말로 고치기", "연구 개념도 글자 고치기", "연구 개념도 기본 그림으로", "연구 개념도 다시 만들기", "연구 개념도 빼기"])
      expect(screen.getByRole("button", { name })).toBeEnabled();
    expect(screen.getByText("밑그림 보기")).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("기본 그림·확인함·뺌 배지, [기본 그림으로]·[확인함] 숨김, [넣기] 표시, 출처 캡션", () => {
    mockFetch({});
    mount({ ...process, included: false });
    expect(screen.getByText("기본 그림")).toBeInTheDocument();
    expect(screen.getByText("확인함")).toBeInTheDocument();
    expect(screen.getByText("뺌")).toBeInTheDocument();
    expect(screen.getByText(process.source_caption)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /기본 그림으로/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /확인함/ })).toBeNull();
    expect(screen.getByRole("button", { name: "추진 체계도 넣기" })).toBeInTheDocument();
  });

  it("오류 배지, disabled 면 모든 버튼 비활성, readOnly 면 [확인함] 만", () => {
    mockFetch({});
    const { unmount } = mount({ ...concept, error: "budget" }, { disabled: true });
    expect(screen.getByText(/오류/)).toHaveTextContent("budget");
    for (const b of screen.getAllByRole("button")) expect(b).toBeDisabled();
    unmount();
    mount(concept, { readOnly: true });
    expect(screen.getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual(["연구 개념도 확인함"]);
  });

  it("[글자 고치기] → 바뀐 칸만 texts 로 POST, 저장 뒤 onApplied(version)", async () => {
    const { calls } = mockFetch({ [url]: saved });
    const { onApplied } = mount(concept);
    await userEvent.click(screen.getByRole("button", { name: "연구 개념도 글자 고치기" }));
    const dialog = screen.getByRole("dialog");
    const first = within(dialog).getByLabelText("제목");
    expect(first).toHaveValue("궤도 틀림 진행 속도 추정");
    expect(within(dialog).getByRole("button", { name: /적용/ })).toBeDisabled();
    await userEvent.clear(first);
    await userEvent.type(first, "진행 속도 추정 개념");
    await userEvent.click(within(dialog).getByRole("button", { name: /적용/ }));
    await waitFor(() => expect(onApplied).toHaveBeenCalledWith(3));
    expect(postBody(calls)).toMatchObject({ action: "texts", texts: { title: "진행 속도 추정 개념" }, base_version: draft.version });
    expect(Object.keys((postBody(calls).texts as Record<string, string>))).toEqual(["title"]);
  });

  it("[확인함] → action confirm", async () => {
    const { calls } = mockFetch({ [url]: saved });
    const { onApplied } = mount(concept);
    await userEvent.click(screen.getByRole("button", { name: "연구 개념도 확인함" }));
    await waitFor(() => expect(onApplied).toHaveBeenCalledWith(3));
    expect(postBody(calls)).toMatchObject({ action: "confirm", base_version: draft.version });
  });

  it("[말로 고치기] → action words + request", async () => {
    const { calls } = mockFetch({ [url]: saved });
    const { onApplied } = mount(concept);
    await userEvent.click(screen.getByRole("button", { name: "연구 개념도 말로 고치기" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "고치기" })).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText("수정 요청"), "화살표를 굵게");
    await userEvent.click(within(dialog).getByRole("button", { name: "고치기" }));
    await waitFor(() => expect(onApplied).toHaveBeenCalledWith(3));
    expect(postBody(calls)).toMatchObject({ action: "words", request: "화살표를 굵게", base_version: draft.version });
  });

  it("[빼기] → exclude, [다시 만들기] → regenerate, [기본 그림으로] → baseline", async () => {
    const { calls } = mockFetch({ [url]: saved });
    mount(concept);
    await userEvent.click(screen.getByRole("button", { name: "연구 개념도 빼기" }));
    await waitFor(() => expect(postBody(calls)).toMatchObject({ action: "exclude" }));
    calls.length = 0;
    await userEvent.click(screen.getByRole("button", { name: "연구 개념도 다시 만들기" }));
    await waitFor(() => expect(postBody(calls)).toMatchObject({ action: "regenerate" }));
    calls.length = 0;
    await userEvent.click(screen.getByRole("button", { name: "연구 개념도 기본 그림으로" }));
    await waitFor(() => expect(postBody(calls)).toMatchObject({ action: "baseline" }));
  });

  it("409 는 카드 안에 detail 로 보이고 onApplied 는 부르지 않는다", async () => {
    mockFetch({ [url]: () => problem(409, "그림을 고치지 못했습니다 (budget)") });
    const { onApplied } = mount(concept);
    await userEvent.click(screen.getByRole("button", { name: "연구 개념도 확인함" }));
    expect(await screen.findByText("그림을 고치지 못했습니다 (budget)")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("(409)");
    expect(onApplied).not.toHaveBeenCalled();
  });
});

describe("FigureList", () => {
  it("섹션별로 거르고, 없으면 아무것도 그리지 않는다; 옛 버전은 ?version=N", () => {
    mockFetch({});
    const { container } = renderWithProviders(
      <>
        <FigureList runId={id} figures={draft.figures} section="objective" baseVersion={2} version={1} readOnly disabled onApplied={() => undefined} />
        <FigureList runId={id} figures={draft.figures} section="policy_importance" baseVersion={2} onApplied={() => undefined} />
        <FigureList runId={id} figures={undefined} section="method" baseVersion={2} onApplied={() => undefined} />
      </>,
    );
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByRole("img", { name: concept.alt })).toHaveAttribute("src", expect.stringContaining("?version=1"));
    expect(container.querySelectorAll("ul")).toHaveLength(1);
  });
});
