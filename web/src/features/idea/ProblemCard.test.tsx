/** ① '핵심 문제' 카드 (ADR 0065, 레인 C) — 4줄·배지·전문가 분석 접힘·줄 고치기(편집 모델)·화면에 열거값 없음. 서버 없이 계약 모양만. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations, renderWithProviders } from "@/test/utils";
import type { CardLines, DiagnoseOut, ProblemCard as Card } from "@/api/types-problem-card";
import { CARD_EDIT_FAILED, CARD_INPUT_CHANGED } from "@/lib/labels";
import { hasInternalId } from "@/lib/docRefs";
import fx from "@/test/fixtures/problem_card.json";
import { ProblemCard, ProblemCardPending } from "./ProblemCard";
import { changeCause, changeCodes, changeContradiction, changeFunction, newCode, type CardChange } from "./ProblemCardModel";

const out = fx as unknown as DiagnoseOut;
const CARD = out.card as Card;
const LINES = out.lines as CardLines;
/** 화면에 나가면 안 되는 열거값 — 신호·확인 경로·확인 필요 사유·방법 이름·항목 이름 */
const INTERNAL_CODES = /unclear_cause|cause_mismatch|unverified|corpus|\bcore\b|function_ko|science_class|needs_check|\bai\b|\buser\b/;

function renderCard(over: Partial<React.ComponentProps<typeof ProblemCard>> = {}) {
  const onEdit = vi.fn<(c: CardChange) => Promise<void>>(async () => undefined);
  const view = renderWithProviders(<ProblemCard card={CARD} lines={LINES} onEdit={onEdit} {...over} />);
  return { ...view, onEdit };
}
const line = (key: string) => screen.getByTestId(`card-line-${key}`);

describe("핵심 문제 카드 — 보기", () => {
  it("4줄(기능 문장·원인·모순·분류)과 배지 — 근거 있음/추정·확인 필요·확인 못 함, 열거값·내부 번호 없음, axe 0", async () => {
    const { container } = renderCard();
    expect(screen.getByRole("heading", { name: "핵심 문제" })).toBeInTheDocument();
    expect(within(line("function")).getByText("궤도 틀림의 진행을 늦춘다")).toBeInTheDocument();
    expect(within(line("function")).getByTestId("card-basis")).toHaveTextContent("근거 있음");
    expect(within(line("cause")).getByText("다짐 효과가 오래 가지 않음")).toBeInTheDocument();
    expect(within(line("cause")).getByTestId("card-needs-check")).toHaveTextContent("확인 필요");
    expect(within(line("function")).queryByTestId("card-needs-check")).toBeNull();
    expect(within(line("contradiction")).getByText("보수 주기 단축 ↔ 보수 비용과 작업 시간 증가")).toBeInTheDocument();
    expect(within(line("contradiction")).getByTestId("card-basis")).toHaveTextContent("추정");
    const codes = within(line("codes")).getAllByTestId("card-code");
    expect(codes.map((c) => c.textContent)).toEqual(["E01B 27/00 궤도 보수 장비", "B61K 9/08확인 못 함", "EI0703 철도 시설"]);
    expect(within(line("codes")).getAllByTestId("card-code-unverified")).toHaveLength(1);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(INTERNAL_CODES);
    expect(hasInternalId(text)).toBe(false);
    await expectNoA11yViolations(container);
  });

  it("전문가 분석은 기본 접힘 — 펼치면 항목 나누기 6칸·사다리 3단·영문 기능 문장·근본 원인 2단계·발명 원리", async () => {
    renderCard();
    const expert = screen.getByTestId("problem-card-expert") as HTMLDetailsElement;
    expect(expert.open).toBe(false);
    await userEvent.click(screen.getByText("전문가 분석 펼치기"));
    expect(expert.open).toBe(true);
    const facets = within(screen.getByTestId("card-facets"));
    for (const label of ["현상", "대상", "장소", "원인", "피해", "원하는 결과"]) expect(facets.getByText(label)).toBeInTheDocument();
    expect(facets.getByText("일반선 자갈 도상 구간")).toBeInTheDocument();
    expect(facets.getByText("(비어 있음)")).toBeInTheDocument(); // 피해 — 근거가 없어 비워 둔 칸
    expect(within(screen.getByTestId("card-ladder")).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "구체: 궤도 틀림 진행 억제",
      "일반화: 선로 구조물의 변형 진행 억제",
      "추상화: 반복 하중을 받는 구조물의 열화 억제",
    ]);
    expect(screen.getByTestId("card-function-en")).toHaveTextContent("slow the progression of track geometry irregularity");
    expect(within(screen.getByTestId("card-causes")).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByTestId("card-principles")).toHaveTextContent("10. 사전 조치");
    expect(screen.getByTestId("card-principles")).toHaveTextContent("35. 속성 변환");
  });

  it("문제 성격·켜진 신호 문구는 화면에 없다 — 접혀 있을 때도 펼친 뒤에도 (1차는 기록만)", async () => {
    const { container } = renderCard();
    const hidden = /문제 성격|켜진 신호|난해|실증형|도입형|연구형|원인이 뚜렷하지 않거나 여러 가지/;
    expect(CARD.nature.kind).toBe("난해");
    expect(CARD.signals).toEqual(["unclear_cause"]);
    expect(out.signal_labels[0]!.label).toMatch(hidden);
    expect(container.textContent).not.toMatch(hidden);
    await userEvent.click(screen.getByText("전문가 분석 펼치기"));
    expect(container.textContent).not.toMatch(hidden);
    expect(screen.queryByTestId("card-nature")).toBeNull();
    expect(screen.queryByTestId("card-signals")).toBeNull();
  });

  it("빈 줄은 '(비어 있음)', 제안자가 고친 줄은 '직접 고침'", () => {
    const card: Card = {
      ...CARD,
      function_ko: { ...CARD.function_ko, origin: "user", value: "틀림 진행을 미리 안다" },
      causes: [],
      contradiction: { ...CARD.contradiction, improve: "", worsen: "", principles: [] },
      ipc: [],
      science_class: [],
    };
    renderCard({ card, lines: { function: "틀림 진행을 미리 안다", cause: "", contradiction: "", codes: "" } });
    expect(within(line("function")).getByTestId("card-by-user")).toHaveTextContent("직접 고침");
    expect(within(line("function")).queryByTestId("card-basis")).toBeNull();
    for (const key of ["cause", "contradiction", "codes"]) {
      expect(within(line(key)).getByTestId("card-line-text")).toHaveTextContent("(비어 있음)");
      expect(within(line(key)).queryByTestId("card-basis")).toBeNull();
    }
  });

  it("입력이 바뀌면 안내 한 줄을 보이고 고치기를 막는다 / 진단 중 표시는 작은 한 줄", () => {
    renderCard({ changed: true });
    expect(screen.getByTestId("problem-card-changed")).toHaveTextContent(CARD_INPUT_CHANGED);
    for (const b of screen.getAllByRole("button", { name: /고치기$/ })) expect(b).toBeDisabled();
    renderWithProviders(<ProblemCardPending />);
    expect(screen.getByTestId("problem-card-pending")).toHaveTextContent("문제 정리 중…");
  });
});

describe("핵심 문제 카드 — 줄 고치기", () => {
  it("기능 문장 [고치기] → 한 칸 → [적용] 이면 그 항목만 고친 카드로 onEdit, 끝나면 편집이 닫힌다", async () => {
    const { onEdit } = renderCard();
    await userEvent.click(screen.getByRole("button", { name: "기능 문장 고치기" }));
    const box = within(line("function")).getByLabelText("기능 문장");
    expect(box).toHaveValue("궤도 틀림의 진행을 늦춘다");
    await userEvent.clear(box);
    await userEvent.type(box, "궤도 틀림의 진행을 미리 알아낸다");
    await userEvent.click(within(line("function")).getByRole("button", { name: "적용" }));
    await waitFor(() => expect(onEdit).toHaveBeenCalledTimes(1));
    const change = onEdit.mock.calls[0]![0];
    expect(change.fields).toEqual(["function_ko"]);
    expect(change.after.function_ko.value).toBe("궤도 틀림의 진행을 미리 알아낸다");
    expect(change.after.causes).toEqual(CARD.causes);
    await waitFor(() => expect(within(line("function")).queryByLabelText("기능 문장")).toBeNull());
  });

  it("바꾼 것이 없으면 서버를 부르지 않고 닫는다 / [취소]", async () => {
    const { onEdit } = renderCard();
    await userEvent.click(screen.getByRole("button", { name: "원인 고치기" }));
    await userEvent.click(within(line("cause")).getByRole("button", { name: "적용" }));
    expect(onEdit).not.toHaveBeenCalled();
    expect(within(line("cause")).queryByLabelText("원인")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "원인 고치기" }));
    await userEvent.click(within(line("cause")).getByRole("button", { name: "취소" }));
    expect(within(line("cause")).queryByLabelText("원인")).toBeNull();
  });

  it("모순은 두 칸 — 비워 두기도 된다", async () => {
    const { onEdit } = renderCard();
    await userEvent.click(screen.getByRole("button", { name: "모순 고치기" }));
    const scope = within(line("contradiction"));
    await userEvent.clear(scope.getByLabelText("좋게 하려는 것"));
    await userEvent.clear(scope.getByLabelText("그 때문에 나빠지는 것"));
    await userEvent.click(scope.getByRole("button", { name: "적용" }));
    await waitFor(() => expect(onEdit).toHaveBeenCalledTimes(1));
    const change = onEdit.mock.calls[0]![0];
    expect(change.fields).toEqual(["contradiction"]);
    expect([change.after.contradiction.improve, change.after.contradiction.worsen]).toEqual(["", ""]);
  });

  it("분류는 코드 추가·삭제 — 바뀐 목록만 fields 에, 상한(특허 분류 3)에서 추가를 막는다", async () => {
    const { onEdit } = renderCard();
    await userEvent.click(screen.getByRole("button", { name: "분류 고치기" }));
    const ipc = within(screen.getByTestId("card-codes-ipc"));
    await userEvent.click(ipc.getByRole("button", { name: "B61K 9/08 삭제" }));
    await userEvent.type(ipc.getByLabelText("특허 분류(IPC) 코드 추가"), "a01m 29/00");
    await userEvent.click(ipc.getByRole("button", { name: "추가" }));
    await userEvent.type(ipc.getByLabelText("특허 분류(IPC) 코드 추가"), "G01B 21/00{Enter}");
    expect(ipc.getByLabelText("특허 분류(IPC) 코드 추가")).toBeDisabled();
    await userEvent.click(within(line("codes")).getByRole("button", { name: "적용" }));
    await waitFor(() => expect(onEdit).toHaveBeenCalledTimes(1));
    const change = onEdit.mock.calls[0]![0];
    expect(change.fields).toEqual(["ipc"]);
    expect(change.after.ipc.map((c) => c.code)).toEqual(["E01B 27/00", "A01M 29/00", "G01B 21/00"]);
    expect(change.after.ipc[1]).toMatchObject({ origin: "user", verified: "unverified", count: null });
    expect(change.after.science_class).toEqual(CARD.science_class);
  });

  it("반영에 실패하면 편집을 연 채 안내한다(고친 글은 그대로)", async () => {
    const onEdit = vi.fn(async () => {
      throw new Error("서버 오류");
    });
    renderCard({ onEdit });
    await userEvent.click(screen.getByRole("button", { name: "원인 고치기" }));
    const box = within(line("cause")).getByLabelText("원인");
    await userEvent.clear(box);
    await userEvent.type(box, "자갈 마모");
    await userEvent.click(within(line("cause")).getByRole("button", { name: "적용" }));
    expect(await screen.findByText(CARD_EDIT_FAILED)).toBeInTheDocument();
    expect(within(line("cause")).getByLabelText("원인")).toHaveValue("자갈 마모");
  });
});

describe("편집 모델", () => {
  it("값만 바꾼다 — 제안자 수정 표시는 서버 몫. 같은 값이면 null", () => {
    expect(changeFunction(CARD, "  궤도 틀림의 진행을   늦춘다 ")).toBeNull();
    const f = changeFunction(CARD, "새 문장")!;
    expect(f.after.function_ko).toEqual({ ...CARD.function_ko, value: "새 문장" });
    expect(changeCause(CARD, CARD.causes[0]!.value)).toBeNull();
    const c = changeCause({ ...CARD, causes: [] }, "새 원인")!;
    expect(c.after.causes).toHaveLength(1);
    expect(c.after.causes[0]!.value).toBe("새 원인");
    expect(changeCause(CARD, "")!.after.causes.map((x) => x.value)).toEqual(["", CARD.causes[1]!.value]);
    expect(changeContradiction(CARD, CARD.contradiction.improve, CARD.contradiction.worsen)).toBeNull();
    expect(changeCodes(CARD, CARD.ipc, CARD.science_class)).toBeNull();
    expect(changeCodes(CARD, CARD.ipc, [])!.fields).toEqual(["science_class"]);
    expect(changeCodes(CARD, [], [])!.fields).toEqual(["ipc", "science_class"]);
    expect(newCode("  ")).toBeNull();
    expect(newCode('<a01m "29/00">')!.code).toBe("A01M 29/00");
    expect("x".repeat(400).length > changeFunction(CARD, "x".repeat(400))!.after.function_ko.value.length).toBe(true);
  });
});
