import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations, mockFetch, problem, renderWithProviders } from "@/test/utils";
import { EvidencePanel } from "./EvidencePanel";
import evidenceFx from "@/test/fixtures/evidence.json";
import version1 from "@/test/fixtures/version1.json";

afterEach(() => vi.unstubAllGlobals());
const id = "20260101000000-00000002";
const citations = [
  { id: "alio:fake-1#0", doc_id: "alio:fake-1", title: "궤도 상태 자동 감지 연구 (가짜)" },
  { id: "openalex:fake-1#0", doc_id: "openalex:fake-1", title: "Track geometry degradation (fake)" },
];

describe("근거 패널", () => {
  it("발췌·배지(세부 확인 필요·이미지 판독·Argon 적합성)·판단 저장(POST evidence-decisions), axe 통과", async () => {
    const { calls } = mockFetch({
      [`/v1/runs/${id}/sentences/s%3Atech_importance%3A0/evidence`]: evidenceFx,
      [`/v1/runs/${id}/evidence-decisions`]: { run_id: id, status: "editing", ...version1, version: 3 },
    });
    const onClose = vi.fn();
    const { container } = renderWithProviders(
      <EvidencePanel runId={id} sentenceId="s:tech_importance:0" sentenceText="선행연구는 틀림 진행 속도를 다루지 않음." citations={citations} baseVersion={2} strategyDraft problems={[{ section: "tech_importance", code: "evidence_mismatch", severity: "warning", message: "근거가 문장을 뒷받침하지 않음", sentence: 0 }]} onClose={onClose} />,
    );
    expect(await screen.findByText("궤도 틀림을 자동으로 감지하는 사내 연구 요약")).toBeInTheDocument();
    expect(screen.getAllByText("세부 확인 필요")).toHaveLength(2);
    expect(screen.getByText("이미지 판독")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /원본 보기/ })).toHaveAttribute("href", "/search?q=openalex%3Afake-1");
    expect(screen.getByText("Argon 부분")).toBeInTheDocument();
    expect(screen.getByText("Argon 불일치")).toBeInTheDocument();
    expect(screen.getByText("승인됨")).toBeInTheDocument();
    expect(screen.getByText("전략체계 초안(확인 전)")).toBeInTheDocument();
    expect(screen.getByText(/Argon 판정: 근거가 문장을 뒷받침하지 않음/)).toBeInTheDocument();
    expect(screen.getByText("알리오 공시 연구보고서")).toBeInTheDocument();
    await expectNoA11yViolations(container);

    const save = screen.getByRole("button", { name: "판단 저장" });
    expect(save).toBeDisabled();
    await userEvent.click(screen.getAllByRole("radio", { name: "승인", hidden: true })[0]!);
    await userEvent.click(screen.getAllByRole("radio", { name: "교체", hidden: true })[1]!);
    expect(screen.getByLabelText(/바꿀 근거/)).toHaveValue("alio:fake-1#0");
    expect(screen.getByText("판단 2건 (v2 기준)")).toBeInTheDocument();
    await userEvent.click(save);
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const post = calls.find((c) => c.url.endsWith("/evidence-decisions"));
    expect(JSON.parse(String(post?.init?.body))).toEqual({
      decisions: [
        { sentence_id: "s:tech_importance:0", evidence_id: "alio:fake-1#0", action: "approve", replacement: null },
        { sentence_id: "s:tech_importance:0", evidence_id: "openalex:fake-1#0", action: "replace", replacement: "alio:fake-1#0" },
      ],
      base_version: 2,
      note: "근거 판단",
    });
  });

  it("409 이면 최신 버전 불러오기 안내, 근거 0건이면 빈 상태", async () => {
    mockFetch({
      [`/v1/runs/${id}/sentences/s%3Atech_importance%3A0/evidence`]: evidenceFx,
      [`/v1/runs/${id}/sentences/s%3Aobjective%3A0/evidence`]: { ...evidenceFx, sentence_id: "s:objective:0", evidence: [] },
      [`/v1/runs/${id}/evidence-decisions`]: () => problem(409, "기준 버전 v2 이 최신이 아닙니다."),
    });
    const { rerender } = renderWithProviders(<EvidencePanel runId={id} sentenceId="s:tech_importance:0" citations={citations} baseVersion={2} onClose={() => undefined} />);
    await screen.findByText("궤도 틀림을 자동으로 감지하는 사내 연구 요약");
    await userEvent.click(screen.getAllByRole("radio", { name: "제외", hidden: true })[0]!);
    await userEvent.click(screen.getByRole("button", { name: "판단 저장" }));
    expect(await screen.findByText("다른 곳에서 먼저 저장되었습니다")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "최신 버전 불러오기" })).toBeInTheDocument();
    rerender(<EvidencePanel runId={id} sentenceId="s:objective:0" citations={citations} baseVersion={2} onClose={() => undefined} />);
    expect(await screen.findByText("이 문장에는 근거가 없습니다")).toBeInTheDocument();
  });
});
