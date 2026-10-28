import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations, mockFetch, renderWithProviders } from "@/test/utils";
import { resetIdea, updateIdea } from "@/features/idea/store";
import { setPolicyChoice } from "@/features/policy/store";
import { emptyRequest } from "@/lib/validation";
import precheckFx from "@/test/fixtures/precheck.json";
import type { ClarifyOutV2, PolicyCardsOut, PrecheckOut } from "@/api/types";
import Clarify from "./Clarify";

const base: ClarifyOutV2 = { questions: [], skip_allowed: true, status: "ok", status_label: "", reason: null, reason_label: null, source: "argon", policy_needed: false };
const CARDS: PolicyCardsOut = {
  cards: [
    {
      id: "government-1",
      direction: "government",
      direction_label: "정부 계획",
      sentences: [{ text: "정부 방향과 이어짐.", evidence: ["molit:a#0"] }],
      sources: [{ chunk_id: "molit:a#0", doc_id: "molit:a", source: "molit", source_label: "국토교통부", title: "계획 (가짜)", year: 2025, page: null, quote: "노후 궤도 보수를 강화함.", url: null }],
    },
  ],
  count: 1,
  status: "ok",
  status_label: "작성안",
  reason: null,
  reason_label: null,
  passages: 1,
  dropped: 0,
  excluded_docs: [],
  transfer: {},
};

function setup() {
  resetIdea();
  setPolicyChoice(null);
  updateIdea({ precheck: { ...(precheckFx as PrecheckOut), blocking: false }, request: { ...emptyRequest(), current_state: "a", root_cause: "b", limitation: "c", goal: "d" } });
}

afterEach(() => vi.unstubAllGlobals());

describe("③ 보강 질문", () => {
  it.each([
    ["off", "보강 질문 없음 — 꺼져 있음"],
    ["enough", "보강 질문 없음 — 입력 충분"],
  ] as const)("질문 없음 사유: %s", async (status, text) => {
    setup();
    mockFetch({ "/v1/precheck/clarify": { ...base, status } });
    renderWithProviders(<Clarify />);
    expect(await screen.findByText(text)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "초안 생성 시작" })).toBeInTheDocument();
  });

  it("생성 실패 → 사유 + [다시 시도]", async () => {
    setup();
    const { calls } = mockFetch({ "/v1/precheck/clarify": { ...base, status: "failed", reason: "error", reason_label: "호출 실패", source: "none" } });
    renderWithProviders(<Clarify />);
    expect(await screen.findByText("보강 질문 없음 — 질문 생성 실패")).toBeInTheDocument();
    expect(screen.getByText("사유: 호출 실패")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    await waitFor(() => expect(calls.filter((c) => c.url === "/v1/precheck/clarify").length).toBe(2));
  });

  it("정책 근거 질문 → 작성안 고르기 → 생성 요청에 policy_choice·보충 정보, axe 0", async () => {
    setup();
    const { calls } = mockFetch({
      "/v1/precheck/clarify": {
        ...base,
        policy_needed: true,
        questions: [
          { id: "policy", question: "정책 근거가 있습니까?", topic: "policy", topic_label: "정책 근거" },
          { id: "q0", question: "적용 노선은?", topic: "target", topic_label: "적용 대상" },
        ],
      },
      "/v1/ideas/policy-cards": CARDS,
      "/v1/runs": { run_id: "20260101000000-00000009", status: "queued" },
    });
    const { container } = renderWithProviders(<Clarify />);
    expect(await screen.findByText("질문 2개")).toBeInTheDocument();
    expect(await screen.findByText("정부 방향과 이어짐.")).toBeInTheDocument();
    await expectNoA11yViolations(container);
    await userEvent.click(screen.getByRole("button", { name: "이 안으로 — 정부 계획" }));
    expect(await screen.findByText("고른 정책 근거: 작성안 그대로")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/적용 노선은/), "경부선");
    await userEvent.click(screen.getByRole("button", { name: "답하고 생성 시작" }));
    await waitFor(() => expect(calls.some((c) => c.url === "/v1/runs")).toBe(true));
    const body = JSON.parse(String(calls.find((c) => c.url === "/v1/runs")!.init!.body));
    expect(body.policy_choice).toMatchObject({ mode: "card", card_ids: ["government-1"] });
    expect(body.supplement).toBe("적용 노선은?: 경부선");
  });
});
