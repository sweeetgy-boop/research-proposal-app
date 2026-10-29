/** 정책 근거를 나중에 다시 넣는 길 (ADR 0052) — ③ 초안 보기 바로가기, ④ 2-가-(1) 머리 [정책 근거 넣기·바꾸기]
 *  (늘 보임·비면 주 색 + 빈칸 안내 줄)·대화상자 직접 입력, ?policy=1 로 바로 열기, ⑥ 제출 전 점검 [정책 근거 넣기]. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useLocation } from "react-router";
import { expectNoA11yViolations, mockFetch, problem, renderWithProviders } from "@/test/utils";
import RunLayout from "./RunLayout";
import Draft from "./Draft";
import Edit from "./Edit";
import SubmitCheck from "./SubmitCheck";
import draftFx from "@/test/fixtures/draft.json";
import reviewFx from "@/test/fixtures/draft_review.json";
import runFx from "@/test/fixtures/run_drafted.json";
import version1 from "@/test/fixtures/version1.json";
import checkFx from "@/test/fixtures/submit_check.json";
import usageFx from "@/test/fixtures/usage.json";

afterEach(() => vi.unstubAllGlobals());

const id = runFx.run_id;
const emptyPolicy = { ...version1, version: 2, sections: version1.sections.map((s) => (s.key === "policy_importance" ? { ...s, sentences: [] } : s)) };
const draftEmpty = { ...draftFx, sections: draftFx.sections.map((s) => (s.key === "policy_importance" ? { ...s, sentences: [] } : s)) };
const NO_CARDS = { cards: [], count: 0, status: "empty", status_label: "해당 없음", reason: null, reason_label: null, passages: 0, dropped: 0, excluded_docs: [], transfer: {} };

function routes(over: Record<string, unknown> = {}) {
  return {
    [`/v1/runs/${id}/draft?version=2`]: emptyPolicy,
    [`/v1/runs/${id}`]: runFx,
    [`/v1/runs/${id}/draft`]: draftEmpty,
    [`/v1/runs/${id}/draft-review`]: reviewFx,
    [`/v1/runs/${id}/outline`]: problem(404, "없음"),
    [`/v1/runs/${id}/draft/working`]: problem(404, "없음"),
    [`/v1/runs/${id}/policy-cards`]: NO_CARDS,
    [`/v1/runs/${id}/changes`]: { total: 0, items: [] },
    [`/v1/runs/${id}/submit-check`]: checkFx,
    [`/v1/runs/${id}/usage`]: usageFx,
    ...over,
  };
}

function Where() {
  const loc = useLocation();
  return <p data-testid="where">{loc.pathname + loc.search}</p>;
}

function mount(route: string) {
  return renderWithProviders(
    <>
      <Routes>
        <Route path="/runs/:id" element={<RunLayout />}>
          <Route path="draft" element={<Draft />} />
          <Route path="edit" element={<Edit />} />
          <Route path="submit-check" element={<SubmitCheck />} />
        </Route>
      </Routes>
      <Routes>
        <Route path="*" element={<Where />} />
      </Routes>
    </>,
    { route, path: "*" },
  );
}

const policyDialog = () => screen.findByRole("dialog", { name: /정책 근거 넣기·바꾸기/ });

describe("④ 직접 수정 — 2-가-(1) 정책 근거", () => {
  it("비어 있으면 머리 버튼이 주 색 + 본문 자리 안내 줄 → 대화상자 직접 입력만 반영 → 새 버전 요청(manual), axe 0", async () => {
    const { calls } = mockFetch(
      routes({
        [`/v1/runs/${id}/policy-choice`]: { run_id: id, version: 3, status: "editing" },
      }),
    );
    const { container } = mount(`/runs/${id}/edit`);
    const head = await screen.findByRole("button", { name: "정책 근거 넣기·바꾸기" });
    expect(head.className).toMatch(/bg-primary/);
    const empty = screen.getByTestId("policy-empty");
    expect(empty).toHaveTextContent("정책 근거가 없습니다");
    await expectNoA11yViolations(container);
    await userEvent.click(within(empty).getByRole("button", { name: "정책 근거 넣기" }));
    const d = await policyDialog();
    expect(await within(d).findByText(/작성안이 없습니다/)).toBeInTheDocument();
    expect(within(d).queryByRole("button", { name: "직접 작성" })).toBeNull(); // 위의 직접 입력 칸 하나로
    await userEvent.type(within(d).getByLabelText("직접 입력 (선택)"), "제4차 철도안전 종합계획에 부합함{enter}노후 궤도 검측 고도화와 이어짐");
    await userEvent.click(within(d).getByRole("button", { name: "직접 입력만 반영" }));
    await waitFor(() => expect(calls.some((c) => c.url === `/v1/runs/${id}/policy-choice`)).toBe(true));
    const body = JSON.parse(String(calls.find((c) => c.url === `/v1/runs/${id}/policy-choice`)!.init?.body));
    expect(body.base_version).toBe(2);
    expect(body.choice.mode).toBe("manual");
    expect(body.choice.sentences.map((s: { text: string }) => s.text)).toEqual(["제4차 철도안전 종합계획에 부합함", "노후 궤도 검측 고도화와 이어짐"]);
  });

  it("채워져 있으면 머리 버튼은 테두리, 안내 줄 없음", async () => {
    mockFetch(routes({ [`/v1/runs/${id}/draft?version=2`]: { ...version1, version: 2 } }));
    mount(`/runs/${id}/edit`);
    const head = await screen.findByRole("button", { name: "정책 근거 넣기·바꾸기" });
    expect(head.className).not.toMatch(/bg-primary /);
    expect(screen.queryByTestId("policy-empty")).toBeNull();
  });

  it("?policy=1 로 들어오면 대화상자가 바로 열리고 주소에서 지운다", async () => {
    mockFetch(routes());
    mount(`/runs/${id}/edit?policy=1`);
    expect(await policyDialog()).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent(new RegExp(`^/runs/${id}/edit$`)));
  });

  it("편집할 수 없는 상태(마무리됨)에도 버튼은 보이고, 누르면 이유", async () => {
    const done = { ...runFx, status: "finalized", flow: { ...runFx.flow, status: "finalized" } };
    mockFetch(routes({ [`/v1/runs/${id}`]: done }));
    mount(`/runs/${id}/edit`);
    await userEvent.click(await screen.findByRole("button", { name: "정책 근거 넣기·바꾸기" }));
    const d = await policyDialog();
    expect(within(d).getByText(/⑥ 최종 마무리에서 다시 연 뒤/)).toBeInTheDocument();
    expect(within(d).getByRole("button", { name: "직접 입력만 반영" })).toBeDisabled();
  });
});

describe("③ 초안 보기·⑥ 제출 전 점검 바로가기", () => {
  it("초안 보기의 빈 2-가-(1) — [정책 근거 넣기 (④ 직접 수정)] 는 ④ 대화상자 주소", async () => {
    mockFetch(routes({ [`/v1/runs/${id}/submit-check`]: problem(404, "없음") }));
    mount(`/runs/${id}/draft`);
    const link = await screen.findByRole("link", { name: "정책 근거 넣기 (④ 직접 수정)" });
    expect(link).toHaveAttribute("href", `/runs/${id}/edit?policy=1`);
  });

  it("제출 전 점검의 [정책 근거] 항목이 확인 필요면 [정책 근거 넣기] → ④ 대화상자, axe 0", async () => {
    const item = { key: "policy_basis", label: "정책 근거", ok: false, detail: "정책 근거 확인 필요 — 정책적 중요도 작성안에서 고르거나 직접 작성", count: 1, target: "section:policy_importance", target_label: "2-가-(1) 정책적 중요도" };
    mockFetch(routes({ [`/v1/runs/${id}/submit-check`]: { ...checkFx, items: [...checkFx.items, item] } }));
    const { container } = mount(`/runs/${id}/submit-check`);
    const go = await screen.findByRole("button", { name: "정책 근거 넣기" });
    expect(screen.getAllByRole("button", { name: "정책 근거 넣기" })).toHaveLength(1);
    await expectNoA11yViolations(container);
    await userEvent.click(go);
    expect(await policyDialog()).toBeInTheDocument(); // ④ 로 가서 대화상자가 열린다
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent(new RegExp(`^/runs/${id}/edit$`)));
  });

  it("[정책 근거] 항목이 통과면 바로가기 없음", async () => {
    const item = { key: "policy_basis", label: "정책 근거", ok: true, detail: "정책적 중요도 작성됨", count: 0, target: null, target_label: null };
    mockFetch(routes({ [`/v1/runs/${id}/submit-check`]: { ...checkFx, items: [...checkFx.items, item] } }));
    mount(`/runs/${id}/submit-check`);
    expect(await screen.findByRole("list", { name: "제출 전 점검 항목" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "정책 근거 넣기" })).toBeNull();
  });
});
