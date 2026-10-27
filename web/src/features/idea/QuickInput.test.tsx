import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations, mockFetch, problem, renderWithProviders } from "@/test/utils";
import { QuickInput } from "./QuickInput";
import structureFx from "@/test/fixtures/structure.json";

afterEach(() => vi.unstubAllGlobals());

function Harness({ onFilled = vi.fn(), onUnavailable = vi.fn() }: { onFilled?: (f: unknown, t: string) => void; onUnavailable?: () => void }) {
  return <QuickInput text="궤도 틀림이 반복 발생함. 검측 이력 기반으로 보수 우선순위를 정하고 싶음." title="궤도 보수" onTextChange={() => undefined} onTitleChange={() => undefined} onFilled={onFilled} onUnavailable={onUnavailable} />;
}

describe("간편 입력", () => {
  it("문장 → 네 칸 미리보기·보완 질문 → 답 반영(merge) → 상세 입력에 채우기, axe 통과", async () => {
    const merged = { ...structureFx, fields: { ...structureFx.fields, root_cause: "다짐 효과가 오래 가지 않음" }, questions: structureFx.questions.slice(1), complete: false };
    const { calls } = mockFetch({
      "/v1/ideas/structure": (init?: RequestInit) => (init?.method === "POST" ? structureFx : problem(405, "x")),
      "/v1/ideas/structure/merge": merged,
    });
    const onFilled = vi.fn();
    const { container } = renderWithProviders(<Harness onFilled={onFilled} />);
    await expectNoA11yViolations(container);
    await userEvent.click(screen.getByRole("button", { name: "네 칸으로 나누기" }));
    expect(await screen.findByRole("heading", { name: "네 칸 미리보기" })).toBeInTheDocument();
    expect(screen.getByText("궤도 틀림이 반복 발생함.")).toBeInTheDocument();
    expect(screen.getByText("보완 질문 2개")).toBeInTheDocument();
    // 서버에 보낸 본문: text·title 만
    const sent = JSON.parse(String(calls.find((c) => c.url === "/v1/ideas/structure")?.init?.body)) as Record<string, string>;
    expect(Object.keys(sent).sort()).toEqual(["text", "title"]);
    await expectNoA11yViolations(container);

    await userEvent.type(screen.getByLabelText(/그 문제가 생기는 원인은/), "다짐 효과가 오래 가지 않음");
    await userEvent.click(screen.getByRole("button", { name: "답 반영" }));
    expect(await screen.findByText("다짐 효과가 오래 가지 않음")).toBeInTheDocument();
    const mergeCall = calls.find((c) => c.url === "/v1/ideas/structure/merge");
    expect(JSON.parse(String(mergeCall?.init?.body))).toEqual({ fields: structureFx.fields, answers: { root_cause: "다짐 효과가 오래 가지 않음" } });
    expect(screen.getByText("보완 질문 1개")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /상세 입력에 채우기/ }));
    expect(onFilled).toHaveBeenCalledWith(merged.fields, "궤도 보수");
  });

  it("503 이면 안내하고 상세 입력으로 되돌린다", async () => {
    mockFetch({ "/v1/ideas/structure": () => problem(503, "간편 입력을 쓸 수 없습니다 (꺼짐 또는 LLM 없음).") });
    const onUnavailable = vi.fn();
    renderWithProviders(<Harness onUnavailable={onUnavailable} />);
    await userEvent.click(screen.getByRole("button", { name: "네 칸으로 나누기" }));
    expect(await screen.findByText("간편 입력을 쓸 수 없습니다")).toBeInTheDocument();
    await waitFor(() => expect(onUnavailable).toHaveBeenCalled());
  });
});
