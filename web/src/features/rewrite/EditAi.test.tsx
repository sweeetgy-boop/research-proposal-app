import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations, mockFetch, renderWithProviders } from "@/test/utils";
import { SectionRewrite } from "./SectionRewrite";
import { SectionQuestions } from "./SectionQuestions";
import { ChangeCount, SaveVersionDialog } from "@/features/versions/SaveVersionFlow";
import rewriteFx from "@/test/fixtures/rewrite.json";

afterEach(() => vi.unstubAllGlobals());
const id = "20260101000000-00000002";

describe("AI 다시 쓰기 (Argon)", () => {
  it("문구·작성자 배지·새 후보 수", async () => {
    mockFetch({ [`/v1/runs/${id}/sections/method/rewrite`]: { ...rewriteFx, new_count: 1, reason: null, mode: "rewrite", writer: { provider: "gemini", model: "argon", local_fallback: false, label: "Argon" } } });
    renderWithProviders(<SectionRewrite runId={id} sectionKey="method" baseVersion={3} onClose={() => undefined} onApplied={() => undefined} />);
    expect(await screen.findByText(/새 후보 1문장/)).toBeInTheDocument();
    expect(screen.getByText("Argon")).toBeInTheDocument();
    expect(screen.getByText(/Argon 이 같은 지시·근거로 다시 씁니다/)).toBeInTheDocument();
  });

  it("후보 0 → 사유 + [다시 시도] (반영 버튼 없음), axe 0", async () => {
    const { calls } = mockFetch({
      [`/v1/runs/${id}/sections/method/rewrite`]: { ...rewriteFx, candidate: [], rows: [], new_count: 0, reason: "error", reason_label: "호출 실패", mode: "rewrite" },
    });
    const { container } = renderWithProviders(<SectionRewrite runId={id} sectionKey="method" baseVersion={3} onClose={() => undefined} onApplied={() => undefined} />);
    expect(await screen.findByText("후보 문장이 없습니다")).toBeInTheDocument();
    expect(screen.getByText("사유: 호출 실패")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /반영/ })).toBeNull();
    await expectNoA11yViolations(container);
    await userEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    await waitFor(() => expect(calls.filter((c) => c.url.endsWith("/rewrite")).length).toBe(2));
  });

  it("빈 정책적 중요도 → 새로 쓰기 제목 + 작성안으로 연결", async () => {
    mockFetch({
      [`/v1/runs/${id}/sections/policy_importance/rewrite`]: {
        ...rewriteFx,
        section: "policy_importance",
        candidate: [],
        rows: [],
        new_count: 0,
        reason: "policy_basis_needed",
        reason_label: "정책 근거가 없어 쓸 수 없습니다 — 정책적 중요도 작성안에서 고르십시오",
        mode: "new",
      },
    });
    const onPolicy = vi.fn();
    renderWithProviders(<SectionRewrite runId={id} sectionKey="policy_importance" baseVersion={3} onClose={() => undefined} onApplied={() => undefined} onPolicy={onPolicy} />);
    expect(await screen.findByText(/AI 새로 쓰기/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다시 시도" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "정책적 중요도 작성안 보기" }));
    expect(onPolicy).toHaveBeenCalled();
  });
});

describe("보완 질문 (Argon)", () => {
  const out = {
    run_id: id,
    section: "tech_importance",
    questions: [{ element: "국외 동향", question: "국외 선행연구는 무엇입니까?" }],
    coverage: 0.5,
    answers: {},
    source: "argon",
    source_label: "Argon 이 본문을 읽고 물음",
    reason: null,
    reason_label: null,
    cached: false,
  };

  it("누가 물었는지 배지, [답 반영해 다시 쓰기] = 답 저장 뒤 다시 쓰기로", async () => {
    const { calls } = mockFetch({
      [`/v1/runs/${id}/sections/tech_importance/questions`]: out,
      [`/v1/runs/${id}/sections/tech_importance/answers`]: { run_id: id, section: "tech_importance", answers: { "국외 동향": "독일 DB" } },
    });
    const onRewrite = vi.fn();
    const { container } = renderWithProviders(<SectionQuestions runId={id} sectionKey="tech_importance" onClose={() => undefined} onRewrite={onRewrite} />);
    expect(await screen.findByText("Argon 이 본문을 읽고 물음")).toBeInTheDocument();
    await expectNoA11yViolations(container);
    await userEvent.type(screen.getByLabelText(/국외 선행연구는/), "독일 DB");
    await userEvent.click(screen.getByRole("button", { name: /답 반영해 다시 쓰기/ }));
    await waitFor(() => expect(onRewrite).toHaveBeenCalledWith("tech_importance"));
    expect(calls.some((c) => c.url.endsWith("/answers"))).toBe(true);
  });

  it("모델 실패 → 체크리스트로 물음 + 사유 + [다시 시도](refresh)", async () => {
    const { calls } = mockFetch({
      [`/v1/runs/${id}/sections/tech_importance/questions`]: { ...out, source: "checklist", source_label: "체크리스트로 물음", reason: "error", reason_label: "호출 실패" },
    });
    renderWithProviders(<SectionQuestions runId={id} sectionKey="tech_importance" onClose={() => undefined} />);
    expect(await screen.findByText(/사유: 호출 실패/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    await waitFor(() => expect(calls.some((c) => c.url.includes("refresh=true"))).toBe(true));
  });
});

describe("새 버전으로 저장", () => {
  it("변경 n건 = 저장 안 한 편집 + 바로 저장된 변경 (종류별)", () => {
    renderWithProviders(
      <ChangeCount
        local={2}
        server={{ run_id: id, base_version: 2, current_version: 4, total: 3, items: [{ type: "figure_confirm", label: "그림 확인", count: 1 }, { type: "evidence_approve", label: "근거 승인", count: 2 }] }}
      />,
    );
    expect(screen.getByText("변경 5건")).toBeInTheDocument();
    expect(screen.getByText("(저장 안 한 편집 2 · 그림 확인 1 · 근거 승인 2)")).toBeInTheDocument();
  });

  it("변경 없음 팝업 — [확인] 은 최종 검토로, [취소] 는 그대로, axe 0", async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    const { container } = renderWithProviders(<SaveVersionDialog open kind="none" onConfirm={onConfirm} onCancel={onCancel} />);
    expect(screen.getByText("변경된 내용이 없습니다. 최종 검토로 넘어갈까요?")).toBeInTheDocument();
    await expectNoA11yViolations(container);
    await userEvent.click(screen.getByRole("button", { name: "확인", hidden: true }));
    expect(onConfirm).toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "취소", hidden: true }));
    expect(onCancel).toHaveBeenCalled();
  });

  it("저장한 뒤 묻기", () => {
    renderWithProviders(<SaveVersionDialog open kind="saved" savedVersion={5} onConfirm={() => undefined} onCancel={() => undefined} />);
    expect(screen.getByText("v5 으로 저장했습니다. 최종 검토로 넘어갈까요?")).toBeInTheDocument();
  });
});
