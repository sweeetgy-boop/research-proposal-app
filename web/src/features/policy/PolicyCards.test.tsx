import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations, renderWithProviders } from "@/test/utils";
import { PolicyCards } from "./PolicyCards";
import { choiceFromCard, editedChoice, mergeCards, seenDocs, splitLines } from "./model";
import type { PolicyCard, PolicyCardsOut, PolicyChoice } from "@/api/types";

const src = (doc: string, quote: string) => ({
  chunk_id: `${doc}#0`,
  doc_id: doc,
  source: doc.split(":")[0]!,
  source_label: "국토교통부",
  title: `${doc} 제목`,
  year: 2025,
  page: "3쪽",
  quote,
  url: `https://example.go.kr/${doc}`,
});
const CARDS: PolicyCard[] = [
  { id: "government-1", direction: "government", direction_label: "정부 계획", sentences: [{ text: "정부 방향과 이어짐.", evidence: ["molit:a#0"] }, { text: "현장 적용으로 기여함.", evidence: ["molit:a#0"] }], sources: [src("molit:a", "노후 궤도 보수를 강화함.")] },
  { id: "company-1", direction: "company", direction_label: "공사 전략", sentences: [{ text: "공사 전략과 이어짐.", evidence: ["korail_web:b#0"] }], sources: [src("korail_web:b", "데이터 기반 유지보수.")] },
];
const OK: PolicyCardsOut = { cards: CARDS, count: 2, status: "ok", status_label: "작성안", reason: null, reason_label: null, passages: 2, dropped: 0, excluded_docs: [], transfer: {} };

describe("정책 작성안 모델", () => {
  it("합치기·직접 수정·문장 나누기·본 문서", () => {
    const m = mergeCards(CARDS[0]!, CARDS[1]!);
    expect(m.mode).toBe("merged");
    expect(m.sentences.map((s) => s.text)).toEqual(["정부 방향과 이어짐.", "현장 적용으로 기여함.", "공사 전략과 이어짐."]);
    expect(m.sources).toHaveLength(2);
    const e = editedChoice(choiceFromCard(CARDS[0]!), "○ 정부 방향과 이어짐.\n새 문장임.");
    expect(e.mode).toBe("edited");
    expect(e.sentences[0]!.evidence).toEqual(["molit:a#0"]);
    expect(e.sentences[1]!.evidence).toEqual([]);
    expect(editedChoice(null, "직접 씀.").mode).toBe("manual");
    expect(splitLines(" - 가\n\n2) 나 ")).toEqual(["가", "나"]);
    expect(seenDocs(CARDS, ["x"])).toEqual(["x", "molit:a", "korail_web:b"]);
  });
});

describe("PolicyCards", () => {
  it("카드(방향·○ 문장·출처 문서명·연도·쪽·인용·링크) → [이 안으로], 두 안 합치기, axe 0", async () => {
    const load = vi.fn(async () => OK);
    const onChoose = vi.fn();
    const { container } = renderWithProviders(<PolicyCards load={load} polish={vi.fn()} value={null} onChoose={onChoose} />);
    expect(await screen.findByText("정부 방향과 이어짐.")).toBeInTheDocument();
    expect(screen.getByText("정부 계획")).toBeInTheDocument();
    expect(screen.getByText("“노후 궤도 보수를 강화함.”")).toBeInTheDocument();
    expect(screen.getAllByText("(국토교통부 · 2025년 · 3쪽)")).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: /원문 보기/ })[0]).toHaveAttribute("href", "https://example.go.kr/molit:a");
    await expectNoA11yViolations(container);
    await userEvent.click(screen.getByRole("button", { name: "이 안으로 — 정부 계획" }));
    expect(onChoose).toHaveBeenLastCalledWith(expect.objectContaining({ mode: "card", card_ids: ["government-1"] }));
    await userEvent.click(screen.getByLabelText(/합치기 선택 — 정부 계획/));
    await userEvent.click(screen.getByLabelText(/합치기 선택 — 공사 전략/));
    await userEvent.click(screen.getByRole("button", { name: "두 안 합치기" }));
    expect(onChoose).toHaveBeenLastCalledWith(expect.objectContaining({ mode: "merged", card_ids: ["government-1", "company-1"] }));
    // [다른 안 보기] — 본 문서를 빼고 다시 요청
    await userEvent.click(screen.getByRole("button", { name: "다른 안 보기" }));
    await waitFor(() => expect(load).toHaveBeenLastCalledWith(["molit:a", "korail_web:b"]));
  });

  it("고른 뒤 직접 수정 + [AI로 다듬기] → [고친 글 적용], [정책 근거 없음으로 진행]", async () => {
    const chosen: PolicyChoice = { mode: "card", card_ids: ["government-1"], sentences: CARDS[0]!.sentences, sources: CARDS[0]!.sources };
    const polish = vi.fn(async (c: PolicyChoice, t: string) => ({ echo: [c.mode, t], choice: { mode: "edited" as const, sentences: [{ text: "다듬은 문장임.", evidence: [] }], sources: chosen.sources }, reason: null, reason_label: null, dropped: 0, transfer: {} }));
    const onChoose = vi.fn();
    const { container } = renderWithProviders(<PolicyCards load={async () => OK} polish={polish} value={chosen} onChoose={onChoose} />);
    expect(await screen.findByText("고른 정책 근거: 작성안 그대로")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "직접 수정" }));
    const box = screen.getByLabelText(/고른 안 고치기/);
    await userEvent.type(box, "\n제안자 추가 문장임.");
    await userEvent.click(screen.getByRole("button", { name: "AI로 다듬기" }));
    await waitFor(() => expect(polish).toHaveBeenCalled());
    expect(polish.mock.calls[0]![1]).toContain("제안자 추가 문장임.");
    await waitFor(() => expect(screen.getByLabelText(/고른 안 고치기/)).toHaveValue("○ 다듬은 문장임."));
    await expectNoA11yViolations(container);
    await userEvent.click(screen.getByRole("button", { name: "고친 글 적용" }));
    expect(onChoose).toHaveBeenLastCalledWith(expect.objectContaining({ mode: "edited", sentences: [{ text: "다듬은 문장임.", evidence: [] }] }));
    await userEvent.click(screen.getByRole("button", { name: "정책 근거 없음으로 진행" }));
    expect(onChoose).toHaveBeenLastCalledWith({ mode: "none", sentences: [], sources: [] });
  });

  it("작성안이 없으면 사유(해당 없음·호출 실패) + [다시 시도], [직접 작성]", async () => {
    const failed: PolicyCardsOut = { ...OK, cards: [], count: 0, status: "failed", status_label: "호출 실패", reason: "error", reason_label: "호출 실패" };
    const load = vi.fn(async () => failed);
    const onChoose = vi.fn();
    renderWithProviders(<PolicyCards load={load} polish={vi.fn()} value={null} onChoose={onChoose} />);
    expect(await screen.findByText(/작성안이 없습니다 — 호출 실패/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
    await userEvent.click(screen.getByRole("button", { name: "직접 작성" }));
    await userEvent.type(screen.getByLabelText(/정책적 중요도 직접 작성/), "직접 쓴 정책 근거임.");
    await userEvent.click(screen.getByRole("button", { name: "고친 글 적용" }));
    expect(onChoose).toHaveBeenLastCalledWith(expect.objectContaining({ mode: "manual", sentences: [{ text: "직접 쓴 정책 근거임.", evidence: [] }] }));
  });

  it("관련 정책 구간이 없으면 해당 없음 (다시 시도 없음)", async () => {
    const empty: PolicyCardsOut = { ...OK, cards: [], count: 0, status: "empty", status_label: "해당 없음 — 관련 구간 없음", reason: "empty", reason_label: "해당 없음" };
    renderWithProviders(<PolicyCards load={async () => empty} polish={vi.fn()} value={null} onChoose={vi.fn()} />);
    expect(await screen.findByText(/작성안이 없습니다 — 해당 없음/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다시 시도" })).toBeNull();
  });
});
