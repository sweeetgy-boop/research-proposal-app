/** 레인 D 화면 — 과제 제목 머리·run 번호 복사, 단계 표시 이동(못 여는 이유·탭 동기화), 제출 전 점검
 *  근거 일괄 승인·제안값 확정, ①·② 입력 변경 대화상자(보기만·관련 섹션만·전체), 내려받기 파일 이름. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { expectNoA11yViolations, mockFetch, problem, renderWithProviders } from "@/test/utils";
import RunLayout from "./RunLayout";
import RunIdea from "./RunIdea";
import RunPrecheck from "./RunPrecheck";
import SubmitCheck from "./SubmitCheck";
import runFx from "@/test/fixtures/run_drafted.json";
import queuedFx from "@/test/fixtures/run_queued.json";
import checkFx from "@/test/fixtures/submit_check.json";
import usageFx from "@/test/fixtures/usage.json";
import precheckFx from "@/test/fixtures/precheck.json";
import { filenameFromDisposition } from "@/api/endpoints-format";
import { canFinalize, runStepFromSub, runStepTargets } from "@/lib/runSteps";
import type { RunState } from "@/api/types";

afterEach(() => vi.unstubAllGlobals());
const id = runFx.run_id;
const REQUEST = { current_state: "궤도 틀림 반복", root_cause: "노반 침하", limitation: "임계치만 봄", goal: "열화 예측", constraints: "", title_hint: "", policy_basis: "", beneficiaries: "", remarks: "", differentiation: "", department: "", budget: null };
// 생성이 멈춘 run (SSE 구독 없이 "초안 전" 상태를 보인다)
const stopped = { ...queuedFx, status: "interrupted", flow: { ...queuedFx.flow, status: "interrupted" } };
const INPUTS = { run_id: id, request: REQUEST, priority_evidence: [], draft_version: 2, status: "drafted" };

function Page({ name }: { name: string }) {
  return <p>{name} 화면</p>;
}

function renderRun(route: string, extra?: React.ReactNode) {
  return renderWithProviders(
    <Routes>
      <Route path="/runs/:id" element={<RunLayout />}>
        <Route index element={<Page name="진행" />} />
        <Route path="draft" element={<Page name="초안" />} />
        <Route path="edit" element={<Page name="수정" />} />
        <Route path="versions" element={<Page name="버전" />} />
        <Route path="final-review" element={<Page name="최종 검토" />} />
        <Route path="finalize" element={<Page name="마무리" />} />
        <Route path="idea" element={<RunIdea />} />
        <Route path="precheck" element={<RunPrecheck />} />
        <Route path="submit-check" element={<SubmitCheck />} />
        {extra}
      </Route>
    </Routes>,
    { route, path: "*" },
  );
}

describe("항목 2 과제 제목", () => {
  it("머리에 두 줄 제목(전체는 title·초점), run 번호와 복사 버튼, axe 0", async () => {
    mockFetch({ [`/v1/runs/${id}`]: runFx });
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    const { container } = renderRun(`/runs/${id}/draft`);
    const title = await screen.findByTestId("run-title");
    expect(title).toHaveClass("line-clamp-2");
    expect(title).toHaveAttribute("title", runFx.title);
    expect(title).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/검측 이력 기반/);
    expect(screen.getByText(id)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "작성 번호 복사" }));
    expect(writeText).toHaveBeenCalledWith(id);
    expect((await screen.findAllByText("작성 번호를 복사했습니다."))[0]).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("제목이 없으면 '제목 미정', 1차 검토 생략은 한국어 사유", async () => {
    mockFetch({ [`/v1/runs/${id}`]: { ...runFx, title: null, flow: { ...runFx.flow, draft_review_skipped: "self_review", draft_review_skipped_label: "1차 검토 생략(같은 모델 작성)" } } });
    renderRun(`/runs/${id}/draft`);
    expect(await screen.findByText("제목 미정")).toBeInTheDocument();
    expect(screen.getByText("1차 검토 생략(같은 모델 작성)")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("self_review");
  });

  it("내려받기 파일 이름은 filename*(한글)을 먼저, 없으면 ASCII", () => {
    const cd = `attachment; filename="proposal-${id}-v3.hwpx"; filename*=UTF-8''${encodeURIComponent("궤도 열화 예측_v3.hwpx")}`;
    expect(filenameFromDisposition(cd, "x.hwpx")).toBe("궤도 열화 예측_v3.hwpx");
    expect(filenameFromDisposition(`attachment; filename="proposal-${id}-v3.hwpx"`, "x")).toBe(`proposal-${id}-v3.hwpx`);
    expect(filenameFromDisposition("attachment; filename*=UTF-8''%E0%A4%A", "x.hwpx")).toBe("x.hwpx");
    expect(filenameFromDisposition(null, "x.hwpx")).toBe("x.hwpx");
  });
});

describe("항목 17 단계 표시 이동", () => {
  it("규칙: 경로 → 단계, 못 여는 이유", () => {
    expect([undefined, "idea", "precheck", "draft", "edit", "versions", "submit-check", "finalize"].map(runStepFromSub)).toEqual([3, 1, 2, 3, 4, 4, 5, 6]);
    const queued = runStepTargets(queuedFx as unknown as RunState);
    expect(queued.find((t) => t.n === 4)).toEqual({ n: 4, to: null, reason: "초안 생성 후 열립니다" });
    expect(queued.find((t) => t.n === 3)?.to).toBe("");
    const drafted = runStepTargets(runFx as unknown as RunState);
    expect(drafted.map((t) => t.to)).toEqual(["idea", "precheck", "draft", "edit", "final-review", null]);
    expect(drafted[5]?.reason).toBe("최종 검토 후 열립니다");
    expect(canFinalize({ ...(runFx as unknown as RunState), flow: { ...(runFx as unknown as RunState).flow, final_reviews: 1 } }).ok).toBe(true);
  });

  it("도달한 단계는 링크(누르면 아래 탭도 켜짐), 못 여는 단계는 이유를 보인다, axe 0", async () => {
    mockFetch({ [`/v1/runs/${id}`]: runFx });
    const { container } = renderRun(`/runs/${id}/draft`);
    const steps = await screen.findByRole("navigation", { name: "작성 단계" });
    const tabs = screen.getByRole("navigation", { name: "제안서 화면 메뉴" });
    expect(within(steps).getByRole("link", { name: /3단계 진행 중:\s*초안 생성/ })).toHaveAttribute("aria-current", "step");
    const finalize = within(steps).getByRole("link", { name: /최종 마무리/ });
    expect(finalize).toHaveAttribute("aria-disabled", "true");
    expect(finalize).not.toHaveAttribute("href");
    expect(finalize).toHaveAccessibleDescription("최종 검토 후 열립니다");
    await userEvent.click(within(steps).getByRole("link", { name: /직접 수정/ }));
    expect(await screen.findByText("수정 화면")).toBeInTheDocument();
    expect(within(tabs).getByRole("link", { name: "직접 수정" })).toHaveAttribute("aria-current", "page");
    expect(within(steps).getByRole("link", { name: /4단계 진행 중:\s*직접 수정/ })).toHaveAttribute("aria-current", "step");
    await userEvent.click(within(steps).getByRole("link", { name: /최종 검토/ }));
    expect(await screen.findByText("최종 검토 화면")).toBeInTheDocument();
    expect(within(tabs).getByRole("link", { name: "최종 검토" })).toHaveAttribute("aria-current", "page");
    await expectNoA11yViolations(container);
  });

  it("생성 중 run: 이후 단계는 '초안 생성 후 열립니다'", async () => {
    mockFetch({ [`/v1/runs/${queuedFx.run_id}`]: stopped });
    renderRun(`/runs/${queuedFx.run_id}`);
    const steps = await screen.findByRole("navigation", { name: "작성 단계" });
    const edit = within(steps).getByRole("link", { name: /직접 수정/ });
    expect(edit).toHaveAttribute("aria-disabled", "true");
    expect(edit).toHaveAccessibleDescription("초안 생성 후 열립니다");
  });
});

describe("항목 17 ①·② 입력 변경 대화상자", () => {
  const PREVIEW = {
    run_id: id,
    fields: [{ field: "constraints", label: "제약 조건" }],
    sections: [
      { key: "method", title: "2-다 연구 방법 및 주요내용" },
      { key: "utilization", title: "4 연구결과 활용계획" },
    ],
    all_sections: 12,
    can_regenerate: true,
    reason: null,
    version: 2,
  };
  const REGEN = {
    run_id: id,
    status: "editing",
    mode: "sections",
    fields: PREVIEW.fields,
    regenerated: PREVIEW.sections,
    failed: [{ key: "title", title: "1-가 연구과제명", reason_label: "빈 응답" }],
    kept: [],
    saved_only: false,
    version: 3,
    origin: "regenerate",
    origin_label: "입력 변경 다시 쓰기",
    note: "입력 변경 — 관련 섹션 다시 쓰기 (제약 조건)",
    created_at: null,
    based_on_review: null,
    reverted_from: null,
    changed_sections: ["method", "utilization"],
    alerts: 0,
    open_annotations: 0,
    annotations: [],
    sections: [],
  };

  it("① 에서 고쳐 저장 → 미리보기 → [관련 섹션만] → regenerate(mode sections, base_version), 초안으로, axe 0", async () => {
    const { calls } = mockFetch({
      [`/v1/runs/${id}`]: runFx,
      [`/v1/runs/${id}/request`]: INPUTS,
      [`/v1/runs/${id}/request/preview`]: PREVIEW,
      [`/v1/runs/${id}/regenerate`]: REGEN,
    });
    const { container } = renderRun(`/runs/${id}/idea`);
    expect(await screen.findByRole("heading", { name: /① 아이디어 입력/ })).toBeInTheDocument();
    expect(await screen.findByDisplayValue("궤도 틀림 반복")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/예산·기간·현장 제약/), "연구기간 1년");
    await userEvent.click(screen.getByRole("button", { name: "입력 저장" }));
    const dialog = await screen.findByRole("dialog", { name: "바뀐 입력을 초안에 반영할까요?" });
    expect(within(dialog).getByText("제약 조건")).toBeInTheDocument();
    expect(within(dialog).getByText("2-다 연구 방법 및 주요내용")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "보기만 하고 돌아가기" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "초안 전체 다시 생성(새 버전, 기존은 이전 버전으로 보존)" })).toBeEnabled();
    await expectNoA11yViolations(container);
    const preview = calls.find((c) => c.url.endsWith("/request/preview"));
    expect(JSON.parse(String(preview?.init?.body)).request.constraints).toBe("연구기간 1년");
    await userEvent.click(within(dialog).getByRole("button", { name: "바뀐 내용과 관련된 섹션만 다시 쓰기(새 버전)" }));
    expect(await screen.findByText("초안 화면")).toBeInTheDocument();
    const body = JSON.parse(String(calls.find((c) => c.url.endsWith("/regenerate"))?.init?.body));
    expect(body).toMatchObject({ mode: "sections", base_version: 2, request: { constraints: "연구기간 1년" } });
    expect((await screen.findAllByText(/새 버전 v3: .*다시 씀 · 이전 내용 유지: 1-가 연구과제명/))[0]).toBeInTheDocument();
  });

  it("[보기만 하고 돌아가기] 는 다시 쓰지 않고, 바뀐 것이 없으면 대화상자 없이 알림", async () => {
    let previewOut: unknown = PREVIEW;
    const { calls } = mockFetch({
      [`/v1/runs/${id}`]: runFx,
      [`/v1/runs/${id}/request`]: INPUTS,
      [`/v1/runs/${id}/request/preview`]: () => previewOut,
    });
    renderRun(`/runs/${id}/idea`);
    await screen.findByDisplayValue("궤도 틀림 반복");
    previewOut = { ...PREVIEW, fields: [], sections: [] };
    await userEvent.click(screen.getByRole("button", { name: "입력 저장" }));
    expect((await screen.findAllByText("바뀐 내용이 없습니다."))[0]).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
    previewOut = PREVIEW;
    await userEvent.click(screen.getByRole("button", { name: "입력 저장" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "보기만 하고 돌아가기" }));
    expect(await screen.findByText("초안 화면")).toBeInTheDocument();
    expect(calls.some((c) => c.url.endsWith("/regenerate"))).toBe(false);
  });

  it("② 에서 차별화 방향을 고쳐 [초안 전체 다시 생성] → mode all, 409 는 배너", async () => {
    let n = 0;
    const { calls } = mockFetch({
      [`/v1/runs/${id}`]: runFx,
      [`/v1/runs/${id}/request`]: INPUTS,
      "/v1/precheck": precheckFx,
      [`/v1/runs/${id}/request/preview`]: { ...PREVIEW, fields: [{ field: "differentiation", label: "차별화 방향" }] },
      [`/v1/runs/${id}/regenerate`]: () => (n++ === 0 ? problem(409, "기준 버전이 다릅니다.") : { ...REGEN, mode: "all", failed: [] }),
    });
    const { container } = renderRun(`/runs/${id}/precheck`);
    expect(await screen.findByRole("heading", { name: /② 유사과제 확인/ })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /유사과제 1건/ })).toBeInTheDocument();
    await expectNoA11yViolations(container);
    await userEvent.type(screen.getByLabelText("차별화 방향"), "열화 속도 추정으로 확장");
    await userEvent.click(screen.getByRole("button", { name: "입력 저장" }));
    const dialog = await screen.findByRole("dialog");
    const all = within(dialog).getByRole("button", { name: /초안 전체 다시 생성/ });
    await userEvent.click(all);
    expect(await within(dialog).findByText("기준 버전이 다릅니다.")).toBeInTheDocument();
    await userEvent.click(all);
    expect(await screen.findByText("초안 화면")).toBeInTheDocument();
    const bodies = calls.filter((c) => c.url.endsWith("/regenerate")).map((c) => JSON.parse(String(c.init?.body)));
    expect(bodies[1]).toMatchObject({ mode: "all", request: { differentiation: "열화 속도 추정으로 확장" } });
  });

  it("초안 전(생성 중)에는 보기 전용 — 저장 버튼이 잠긴다", async () => {
    mockFetch({ [`/v1/runs/${queuedFx.run_id}`]: stopped, [`/v1/runs/${queuedFx.run_id}/request`]: { ...INPUTS, run_id: queuedFx.run_id, draft_version: 0 } });
    renderRun(`/runs/${queuedFx.run_id}/idea`);
    expect(await screen.findByText("보기 전용")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "입력 저장" })).toBeDisabled();
  });
});

describe("항목 16 제출 전 점검 동작", () => {
  it("[근거 일괄 승인] 은 base_version 과 함께, [제안값 그대로 확정] 은 confirm 으로", async () => {
    const { calls } = mockFetch({
      [`/v1/runs/${id}`]: runFx,
      [`/v1/runs/${id}/submit-check`]: checkFx,
      [`/v1/runs/${id}/usage`]: usageFx,
      [`/v1/runs/${id}/evidence-decisions/bulk-approve`]: { run_id: id, status: "editing", version: 3, sections: [], annotations: [] },
      [`/v1/runs/${id}/confirm`]: { run_id: id, confirmed: { task_type: ["applied"] } },
    });
    const { container } = renderRun(`/runs/${id}/submit-check`);
    expect(await screen.findByText(/확인 필요 1문장/)).toBeInTheDocument();
    expect(screen.queryByText(/0\/\d+|승인 \d+\/\d+/)).toBeNull();
    expect(screen.getByText(/AI 제안값: 응용연구/)).toBeInTheDocument();
    await expectNoA11yViolations(container);
    await userEvent.click(screen.getByRole("button", { name: "근거 일괄 승인 (1건)" }));
    expect((await screen.findAllByText("근거 1건을 승인했습니다."))[0]).toBeInTheDocument();
    const bulk = calls.find((c) => c.url.endsWith("/bulk-approve"));
    expect(JSON.parse(String(bulk?.init?.body))).toEqual({ base_version: 2 });
    await userEvent.click(screen.getByRole("button", { name: "제안값 그대로 확정" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/confirm"))).toBe(true));
    expect(JSON.parse(String(calls.find((c) => c.url.endsWith("/confirm"))?.init?.body))).toEqual({ task_type: "applied" });
    // 직접 고르기: 활용계획은 체크칸, min~max 안에서 확정
    await userEvent.click(screen.getByRole("button", { name: "다시 고르기" }));
    await userEvent.click(screen.getByRole("checkbox", { name: /매뉴얼 작성/ }));
    await userEvent.click(screen.getByRole("button", { name: "고른 값으로 확정" }));
    await waitFor(() => expect(calls.filter((c) => c.url.endsWith("/confirm"))).toHaveLength(2));
    expect(JSON.parse(String(calls.filter((c) => c.url.endsWith("/confirm"))[1]?.init?.body))).toEqual({ utilization: ["software", "manual"] });
  });
});
