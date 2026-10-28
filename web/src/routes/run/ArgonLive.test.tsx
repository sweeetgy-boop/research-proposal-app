/** [3] Argon 우선 작성 — "로컬 작성" 배지(초안 보기·직접 수정)·근거 대조(로컬) 불일치·run 머리 칩,
 *  [4] 실시간 검색 — 인용 문서·근거 패널의 "실시간 검색" 배지. 필드가 없으면(옛 run) 그대로. */
import { screen, within } from "@testing-library/react";
import { Route, Routes } from "react-router";
import { expectNoA11yViolations, mockFetch, problem, renderWithProviders } from "@/test/utils";
import RunLayout from "./RunLayout";
import Draft from "./Draft";
import Edit from "./Edit";
import { EvidencePanel } from "@/features/evidence/EvidencePanel";
import draftFx from "@/test/fixtures/draft.json";
import reviewFx from "@/test/fixtures/draft_review.json";
import runFx from "@/test/fixtures/run_drafted.json";
import version1 from "@/test/fixtures/version1.json";
import evidenceFx from "@/test/fixtures/evidence.json";
import { localWriterNote } from "@/lib/writer";

afterEach(() => vi.unstubAllGlobals());

const id = runFx.run_id;
const argonDraft = {
  ...draftFx,
  writers: {
    title: { provider: "gemini", model: "gemini-4-argon", local_fallback: false, reason: null },
    objective: { provider: "mlx", model: "qwen-7b", local_fallback: true, reason: "error" },
    method: { provider: "mlx", model: "qwen-7b", local_fallback: true, reason: "rate_limit" },
    expected_technology: { provider: "mlx", model: "qwen-7b", local_fallback: true, reason: "budget" },
    utilization: { provider: "mlx", model: "qwen-7b", local_fallback: true, reason: "invalid" },
  },
  local_sections: ["objective", "method", "expected_technology", "utilization"],
  local_check: { enabled: true, mismatches: 2, skipped_sections: ["title"] },
  fallback_sections: [{ key: "tech_importance", provider: "gemini", model: "gemini-4-argon", reason: "empty" }],
  citations: [...draftFx.citations.map((c) => ({ ...c, live: false })), { id: "scienceon:live-1#0", doc_id: "scienceon:live-1", title: "실시간 논문 (가짜)", live: true }],
  problems: [
    ...draftFx.problems,
    { section: "objective", code: "local_evidence_mismatch", severity: "warning", message: "로컬 대조: 근거와 맞지 않음", sentence: null },
  ],
};
const argonRun = { ...runFx, writer: "gemini", local_sections: argonDraft.local_sections };

function routes(draft: unknown, run: unknown) {
  return {
    [`/v1/runs/${id}/draft?version=2`]: { ...version1, version: 2 },
    [`/v1/runs/${id}`]: run,
    [`/v1/runs/${id}/draft`]: draft,
    [`/v1/runs/${id}/draft-review`]: reviewFx,
    [`/v1/runs/${id}/outline`]: problem(404, "설계도가 없습니다"),
    [`/v1/runs/${id}/submit-check`]: problem(404, "없음"),
    [`/v1/runs/${id}/draft/working`]: problem(404, "없음"),
  };
}

function mount(sub: "draft" | "edit") {
  return renderWithProviders(
    <Routes>
      <Route path="/runs/:id" element={<RunLayout />}>
        <Route path="draft" element={<Draft />} />
        <Route path="edit" element={<Edit />} />
      </Route>
    </Routes>,
    { route: `/runs/${id}/${sub}`, path: "*" },
  );
}

const heading = (name: RegExp) => screen.getByRole("heading", { level: 3, name });

describe("[3] 로컬 작성 배지", () => {
  it("초안 보기: local_sections 섹션에만 배지, 사유 라벨(오류·호출 한도·일일 상한·형식 오류), 대체 작성 유지, 근거 대조(로컬) 건수 (axe 0)", async () => {
    mockFetch(routes(argonDraft, argonRun));
    const { container } = mount("draft");
    expect(await screen.findByRole("heading", { name: "초안 본문" })).toBeInTheDocument();
    const cases: [RegExp, string][] = [
      [/^2-나 연구목적/, "오류"],
      [/^2-다 연구 방법/, "호출 한도"],
      [/^3-나 기대효과 \(기술혁신/, "일일 상한"],
      [/^4 연구결과 활용계획/, "형식 오류"],
    ];
    for (const [name, reason] of cases) {
      const h = heading(name);
      const badge = within(h).getByText("로컬 작성");
      expect(badge).toHaveAttribute("title", `Argon 작성 실패(${reason}) 뒤 로컬 모델이 작성`);
      expect(h).toHaveTextContent(`(Argon 작성 실패(${reason}) 뒤 로컬 모델이 작성)`); // sr-only — 배지만으로 뜻을 전하지 않는다
    }
    expect(within(heading(/^1-가 연구과제명/)).queryByText("로컬 작성")).toBeNull();
    expect(within(heading(/^2-가-\(2\) 기술적 중요도/)).getByText("대체 작성")).toHaveAttribute("title", expect.stringContaining("gemini/gemini-4-argon"));
    // 알림 영역: 근거 대조(로컬) 불일치 2건 + 문제 항목 라벨 + 건너뛴 섹션
    expect(screen.getByTestId("local-check")).toHaveTextContent("근거 대조(로컬) 불일치 2건");
    expect(screen.getByTestId("local-check")).toHaveTextContent("대조 건너뜀: 1-가 연구과제명");
    expect(screen.getByRole("heading", { name: /알림 2건/ })).toBeInTheDocument();
    expect(screen.getAllByText("근거 대조(로컬) 불일치")).toHaveLength(1);
    // run 머리 칩 (작게)
    expect(screen.getByText("Argon 작성 · 로컬 4개 섹션")).toBeInTheDocument();
    // [4] 인용 문서: live 인용에만 배지
    const cites = within(screen.getByRole("region", { name: /인용 문서 2건/ })).getAllByRole("listitem");
    expect(within(cites[0]!).queryByText("실시간 검색")).toBeNull();
    expect(within(cites[1]!).getByText("실시간 검색")).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("직접 수정: 섹션 제목 옆에 같은 배지", async () => {
    mockFetch(routes(argonDraft, { ...argonRun, writer: "local" }));
    mount("edit");
    expect(await screen.findByRole("heading", { level: 3, name: /^2-나 연구목적/ })).toBeInTheDocument();
    expect(within(heading(/^2-나 연구목적/)).getByText("로컬 작성")).toHaveAttribute("title", localWriterNote({ provider: "mlx", model: "q", local_fallback: true, reason: "error" }));
    expect(within(heading(/^1-가 연구과제명/)).queryByText("로컬 작성")).toBeNull();
    expect(within(heading(/^2-가-\(2\) 기술적 중요도/)).getByText("대체 작성")).toBeInTheDocument();
    // writer=local 이면 run 머리 칩은 "로컬 작성"
    const header = screen.getByRole("heading", { level: 1 }).parentElement!;
    expect(within(header).getByText("로컬 작성")).toBeInTheDocument();
  });

  it("옛 run(필드 없음): 로컬 작성 배지·대조 건수·칩·실시간 배지가 없다", async () => {
    mockFetch(routes(draftFx, runFx));
    mount("draft");
    expect(await screen.findByRole("heading", { name: "초안 본문" })).toBeInTheDocument();
    // 문장 origin 배지(llm → "로컬 작성")와 별개로, 섹션 머리·run 머리에는 없다
    for (const h of screen.getAllByRole("heading", { level: 3 })) expect(within(h).queryByText("로컬 작성")).toBeNull();
    expect(within(screen.getByRole("heading", { level: 1 }).parentElement!).queryByText(/로컬 작성|Argon 작성/)).toBeNull();
    expect(screen.queryByTestId("local-check")).toBeNull();
    expect(screen.queryByText("실시간 검색")).toBeNull();
  });
});

describe("[4] 근거 패널 실시간 검색 배지", () => {
  it("live 근거에만 배지 (axe 0)", async () => {
    const fx = { ...evidenceFx, evidence: evidenceFx.evidence.map((e, i) => ({ ...e, live: i === 1 })) };
    mockFetch({ [`/v1/runs/${id}/sentences/s%3Atech_importance%3A0/evidence`]: fx });
    const { container } = renderWithProviders(
      <EvidencePanel runId={id} sentenceId="s:tech_importance:0" citations={[]} baseVersion={2} onClose={() => {}} />,
    );
    expect(await screen.findByText("궤도 틀림을 자동으로 감지하는 사내 연구 요약")).toBeInTheDocument();
    expect(screen.getAllByText("실시간 검색")).toHaveLength(1);
    const groups = screen.getAllByRole("group", { hidden: true });
    expect(groups.length).toBeGreaterThan(0);
    await expectNoA11yViolations(container);
  });
});
