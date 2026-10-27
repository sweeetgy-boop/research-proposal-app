import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations, mockFetch, problem, renderWithProviders } from "@/test/utils";
import { SectionRewrite } from "./SectionRewrite";
import { SectionQuestions } from "./SectionQuestions";
import { defaultChosen } from "./model";
import rewriteFx from "@/test/fixtures/rewrite.json";
import questionsFx from "@/test/fixtures/questions.json";
import version1 from "@/test/fixtures/version1.json";
import type { RewriteOut } from "@/api/types";

afterEach(() => vi.unstubAllGlobals());
const id = "20260101000000-00000002";

describe("섹션 AI 다시 쓰기", () => {
  it("기본 선택은 보존이 아닌 후보 행", () => {
    expect(defaultChosen(rewriteFx as RewriteOut)).toEqual([0]);
  });

  it("현재·후보 나란히, 보존 배지, 고른 행만 반영(POST apply chosen·base_version), axe 통과", async () => {
    const { calls } = mockFetch({
      [`/v1/runs/${id}/sections/method/rewrite`]: rewriteFx,
      [`/v1/runs/${id}/sections/method/rewrite/apply`]: { run_id: id, status: "editing", ...version1, version: 4 },
    });
    const onApplied = vi.fn();
    const { container } = renderWithProviders(<SectionRewrite runId={id} sectionKey="method" baseVersion={3} onClose={() => undefined} onApplied={onApplied} />);
    expect(await screen.findByText("검측 이력을 분석해 구간별 진행 속도를 추정함.")).toBeInTheDocument();
    expect(screen.getByText("경부선 구간의 검측 이력을 분석해 구간별 진행 속도를 추정함.")).toBeInTheDocument();
    expect(screen.getByText("보존")).toBeInTheDocument();
    const boxes = screen.getAllByRole("checkbox", { hidden: true });
    expect(boxes[0]).toBeChecked();
    expect(boxes[1]).toBeChecked();
    expect(boxes[1]).toBeDisabled();
    await expectNoA11yViolations(container);
    await userEvent.click(screen.getByRole("button", { name: /고른 1문장 반영/ }));
    await waitFor(() => expect(onApplied).toHaveBeenCalledWith(4));
    const post = calls.find((c) => c.url.endsWith("/rewrite/apply"));
    expect(JSON.parse(String(post?.init?.body))).toEqual({ chosen: [0], base_version: 3, note: "" });
  });

  it("503 이면 안내만 (반영 버튼 없음), 임시 편집이 있으면 반영 막음", async () => {
    mockFetch({ [`/v1/runs/${id}/sections/method/rewrite`]: () => problem(503, "섹션 다시 쓰기가 꺼져 있습니다") });
    renderWithProviders(<SectionRewrite runId={id} sectionKey="method" baseVersion={3} dirty onClose={() => undefined} onApplied={() => undefined} />);
    expect(await screen.findByText("AI 다시 쓰기를 쓸 수 없습니다")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /반영/ })).toBeNull();
    expect(screen.getByText("저장하지 않은 편집이 있습니다")).toBeInTheDocument();
  });
});

describe("보완 질문", () => {
  it("질문·충족률 표시, 답 저장 POST answers", async () => {
    const { calls } = mockFetch({
      [`/v1/runs/${id}/sections/method/questions`]: questionsFx,
      [`/v1/runs/${id}/sections/method/answers`]: { run_id: id, section: "method", answers: { 산출물: "1차년도 보고서" } },
    });
    const { container } = renderWithProviders(<SectionQuestions runId={id} sectionKey="method" onClose={() => undefined} />);
    expect(await screen.findByText("체크리스트 충족 50%")).toBeInTheDocument();
    await expectNoA11yViolations(container);
    await userEvent.type(screen.getByLabelText(/단계마다 나오는 산출물/), "1차년도 보고서");
    await userEvent.click(screen.getByRole("button", { name: "답 저장" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/answers"))).toBe(true));
    const post = calls.find((c) => c.url.endsWith("/answers"));
    expect(JSON.parse(String(post?.init?.body))).toEqual({ answers: { 산출물: "1차년도 보고서" } });
  });
});
