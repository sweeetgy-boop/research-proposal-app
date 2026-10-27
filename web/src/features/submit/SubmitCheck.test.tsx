import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { expectNoA11yViolations, mockFetch, problem, renderWithProviders } from "@/test/utils";
import { targetPath } from "./targets";
import { SubmitCheckList } from "./SubmitCheckList";
import SubmitCheck from "@/routes/run/SubmitCheck";
import RunLayout from "@/routes/run/RunLayout";
import checkFx from "@/test/fixtures/submit_check.json";
import usageFx from "@/test/fixtures/usage.json";
import runFx from "@/test/fixtures/run_final_reviewed.json";
import type { SubmitCheckOut } from "@/api/types";

afterEach(() => vi.unstubAllGlobals());
const id = runFx.run_id;

describe("제출 전 점검", () => {
  it("target → 경로", () => {
    expect(targetPath(id, "section:method")).toBe(`/runs/${id}/draft#sec-method`);
    expect(targetPath(id, "sentence:s:method:0")).toBe(`/runs/${id}/draft?evidence=s%3Amethod%3A0`);
    expect(targetPath(id, "route:evidence")).toBe(`/runs/${id}/draft`);
    expect(targetPath(id, "route:final-review")).toBe(`/runs/${id}/final-review`);
    expect(targetPath(id, null)).toBeNull();
  });

  it("항목 목록: 통과/확인 필요, 누르면 target 으로, axe 통과", async () => {
    const onGo = vi.fn();
    const { container } = renderWithProviders(<SubmitCheckList check={checkFx as SubmitCheckOut} runId={id} onGo={onGo} />);
    expect(screen.getAllByText("확인 필요")).toHaveLength(4);
    expect(screen.getAllByText("통과")).toHaveLength(5);
    await userEvent.click(screen.getByRole("button", { name: /미해결 알림: 확인 필요/ }));
    expect(onGo).toHaveBeenCalledWith(`/runs/${id}/draft#sec-policy_importance`);
    await userEvent.click(screen.getByRole("button", { name: /남은 검토 메모/ }));
    expect(onGo).toHaveBeenCalledWith(`/runs/${id}/draft?evidence=s%3Amethod%3A0`);
    expect(screen.queryByRole("button", { name: /필수 섹션/ })).toBeNull();
    await expectNoA11yViolations(container);
  });

  it("화면: 점검·사용 기록·만족도(마무리 뒤) → POST feedback, 422 는 배너", async () => {
    const finalized = { ...runFx, status: "finalized", flow: { ...runFx.flow, status: "finalized" } };
    let fb = 0;
    const { calls } = mockFetch({
      [`/v1/runs/${id}`]: finalized,
      [`/v1/runs/${id}/submit-check`]: checkFx,
      [`/v1/runs/${id}/usage`]: usageFx,
      [`/v1/runs/${id}/feedback`]: () => (fb++ === 0 ? problem(422, "이메일·전화번호는 넣을 수 없습니다.") : { ...usageFx, usage: { ...usageFx.usage, satisfaction: { score: 4, comment: "좋음", recorded_at: null } } }),
    });
    const { container } = renderWithProviders(
      <Routes>
        <Route path="/runs/:id" element={<RunLayout />}>
          <Route path="submit-check" element={<SubmitCheck />} />
        </Route>
      </Routes>,
      { route: `/runs/${id}/submit-check`, path: "*" },
    );
    expect(await screen.findByRole("heading", { name: "제출 전 점검" })).toBeInTheDocument();
    expect(await screen.findByText("확인 필요 4건")).toBeInTheDocument();
    expect(await screen.findByText("54초")).toBeInTheDocument();
    expect(screen.getByText(/승인 1 · 교체 0 · 제외 0 \/ 2/)).toBeInTheDocument();
    await expectNoA11yViolations(container);
    await userEvent.click(screen.getByRole("radio", { name: "4" }));
    await userEvent.type(screen.getByLabelText(/한 줄 소감/), "좋음");
    await userEvent.click(screen.getByRole("button", { name: "만족도 보내기" }));
    expect(await screen.findByText("이메일·전화번호는 넣을 수 없습니다.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "만족도 보내기" }));
    await waitFor(() => expect(screen.getByText(/기록됨: 4\/5 — 좋음/)).toBeInTheDocument());
    expect(JSON.parse(String(calls.find((c) => c.url.endsWith("/feedback"))?.init?.body))).toEqual({ score: 4, comment: "좋음" });
  });
});
