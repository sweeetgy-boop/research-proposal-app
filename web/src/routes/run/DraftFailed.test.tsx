/** 빈 초안 금지(ADR 0027): 실패 섹션은 "생성 실패" 배지 + [이 섹션 다시 생성] → U3 rewrite/apply 재사용. */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { expectNoA11yViolations, mockFetch, problem, renderWithProviders } from "@/test/utils";
import RunLayout from "./RunLayout";
import Draft from "./Draft";
import draftFx from "@/test/fixtures/draft.json";
import reviewFx from "@/test/fixtures/draft_review.json";
import runFx from "@/test/fixtures/run_drafted.json";
import rewriteFx from "@/test/fixtures/rewrite.json";
import version1 from "@/test/fixtures/version1.json";

afterEach(() => vi.unstubAllGlobals());

const id = runFx.run_id;
const failedDraft = {
  ...draftFx,
  sections: draftFx.sections.map((s) => (s.key === "method" ? { ...s, sentences: [] } : s)),
  failed_sections: [{ key: "method", reason: "json", label: "JSON 문법 오류(잘린 응답 포함)" }],
  fallback_sections: [{ key: "title", provider: "gemini", model: "gemini-4-argon", reason: "empty" }],
  problems: [{ section: "method", code: "generation_failed", severity: "warning", message: "생성 실패(JSON 문법 오류) — 이 섹션을 다시 생성하십시오", sentence: null }],
};

function mount() {
  return renderWithProviders(
    <Routes>
      <Route path="/runs/:id" element={<RunLayout />}>
        <Route path="draft" element={<Draft />} />
      </Route>
    </Routes>,
    { route: `/runs/${id}/draft`, path: "*" },
  );
}

describe("초안 보기 — 생성 실패 섹션", () => {
  it("실패 배지·사유·요약 알림을 보이고 [이 섹션 다시 생성] 이 rewrite → apply 로 새 버전을 만든다, axe 통과", async () => {
    const { calls } = mockFetch({
      [`/v1/runs/${id}`]: runFx,
      [`/v1/runs/${id}/draft`]: failedDraft,
      [`/v1/runs/${id}/draft-review`]: reviewFx,
      [`/v1/runs/${id}/outline`]: problem(404, "설계도가 없습니다"),
      [`/v1/runs/${id}/submit-check`]: problem(404, "없음"),
      [`/v1/runs/${id}/sections/method/rewrite`]: { ...rewriteFx, section: "method" },
      [`/v1/runs/${id}/sections/method/rewrite/apply`]: { run_id: id, status: "editing", ...version1, version: 2 },
    });
    const { container } = mount();
    expect(await screen.findByText(/생성 실패 섹션 1개/)).toBeInTheDocument();
    expect(screen.getByText("생성 실패")).toBeInTheDocument();
    expect(screen.getByText(/JSON 문법 오류\(잘린 응답 포함\) — 빈칸으로 두었습니다/)).toBeInTheDocument();
    expect(screen.getByText("대체 작성")).toHaveAttribute("title", expect.stringContaining("gemini/gemini-4-argon"));
    await expectNoA11yViolations(container);
    await userEvent.click(screen.getByRole("button", { name: /이 섹션 다시 생성/ }));
    expect(await screen.findByText("검측 이력을 분석해 구간별 진행 속도를 추정함.")).toBeInTheDocument();
    expect(calls.some((c) => c.url.endsWith("/sections/method/rewrite") && c.init?.method === "POST")).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: /반영/ }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/rewrite/apply"))).toBe(true));
    const post = calls.find((c) => c.url.endsWith("/rewrite/apply"));
    expect(JSON.parse(String(post?.init?.body))).toMatchObject({ base_version: draftFx.version });
  });

  it("실패 섹션이 없으면 배지·버튼이 없다", async () => {
    mockFetch({
      [`/v1/runs/${id}`]: runFx,
      [`/v1/runs/${id}/draft`]: draftFx,
      [`/v1/runs/${id}/draft-review`]: reviewFx,
      [`/v1/runs/${id}/outline`]: problem(404, "설계도가 없습니다"),
      [`/v1/runs/${id}/submit-check`]: problem(404, "없음"),
    });
    mount();
    expect(await screen.findByRole("heading", { name: "초안 본문" })).toBeInTheDocument();
    expect(screen.queryByText("생성 실패")).toBeNull();
    expect(screen.queryByText("대체 작성")).toBeNull();
    expect(screen.queryByRole("button", { name: /이 섹션 다시 생성/ })).toBeNull();
  });
});
