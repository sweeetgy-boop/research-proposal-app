/** 문제 정의 카드의 화면 흐름 (ADR 0065, 레인 C) — ① 뒤에서 진단·꺼짐/실패면 카드 없음·[다음] 은 기다리지 않음·줄 고치기 반영,
 *  ② "문제 정의가 바뀌었습니다" 한 줄(자동 재생성 없음)·과제명의 발명 원리 배지, 옛 화면 상태 호환. API 는 mock(서버는 레인 A). */
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useLocation } from "react-router";
import { mockFetch, problem, renderWithProviders } from "@/test/utils";
import { clearSession } from "@/auth/session";
import type { CardEditOut, DiagnoseOut, ProblemCard as Card } from "@/api/types-problem-card";
import type { PrecheckOut } from "@/api/types";
import type { NovelRecommendations } from "@/api/types-novel";
import { DIAGNOSE_EDIT_PATH, DIAGNOSE_PATH } from "@/api/problemCard";
import { fourSignature, getIdea, resetIdea, updateIdea, updateRequest, withoutCard } from "@/features/idea/store";
import { DIAGNOSE_DEBOUNCE_MS, usableCard } from "@/features/idea/ProblemCardDiagnosis";
import { PlanCards } from "@/features/precheck/PlanCards";
import { CARD_INPUT_CHANGED, PLANS_STALE_NOTE } from "@/lib/labels";
import { emptyRequest } from "@/lib/validation";
import structureFx from "@/test/fixtures/structure.json";
import precheckFx from "@/test/fixtures/precheck.json";
import fx from "@/test/fixtures/problem_card.json";
import Idea from "@/routes/Idea";
import Precheck from "@/routes/Precheck";

const OK = fx as unknown as DiagnoseOut;
const CARD = OK.card as Card;
const FIELDS = { current_state: "궤도 틀림이 반복 발생함", root_cause: "다짐 효과가 오래 가지 않음", limitation: "주기적 보수로는 진행 속도를 반영하지 못함", goal: "검측 이력 기반 보수 우선순위 산정" };
const FULL = { ...structureFx, fields: FIELDS, questions: [], complete: true };
const OFF: DiagnoseOut = { ...OK, status: "off", card: null, lines: null, signal_labels: [], provider: null, model: null };
const PRE_PLAIN = { ...precheckFx, recommendations: undefined };
const body = (init?: RequestInit) => JSON.parse(String(init?.body)) as Record<string, unknown>;

/** mockFetch 위에 한 경로만 "응답을 붙잡아 두는" fetch 를 덧씌운다 — release 로 풀고, signal 로 끊김을 본다 */
function holdFetch(path: string) {
  const inner = globalThis.fetch;
  const held: { signal?: AbortSignal | null; release: (v: unknown) => void; calls: number } = { release: () => undefined, calls: 0 };
  vi.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input) !== path) return inner(input, init);
    held.calls += 1;
    held.signal = init?.signal;
    return new Promise<Response>((resolve, reject) => {
      held.release = (v) => resolve(new Response(JSON.stringify(v), { status: 200, headers: { "content-type": "application/json" } }));
      init?.signal?.addEventListener("abort", () => reject(new DOMException("끊김", "AbortError")));
    });
  });
  return held;
}

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>;
}
function renderIdea() {
  return renderWithProviders(
    <Routes>
      <Route path="/new" element={<Idea />} />
      <Route path="*" element={<Where />} />
    </Routes>,
    { route: "/new" },
  );
}
/** 상세 입력에 네 칸이 찬 상태로 시작 — 정책 근거가 있어 [다음] 에 팝업이 끼지 않는다 */
function startDetail(over: Record<string, unknown> = {}) {
  updateIdea({ inputMode: "detail", request: { ...emptyRequest(), ...FIELDS, policy_basis: "철도안전 종합계획" }, ...over });
}
const WAIT = { timeout: DIAGNOSE_DEBOUNCE_MS + 2000 };

beforeEach(() => resetIdea());
afterEach(() => {
  vi.unstubAllGlobals();
  clearSession();
  resetIdea();
});

describe("① 진단을 뒤에서", () => {
  it("간편 입력으로 네 칸을 채우면 바로 진단 — 정책 근거 팝업이 떠 있어도 카드 4줄이 채워진다", async () => {
    const { calls } = mockFetch({ "/v1/ideas/structure": FULL, "/v1/ideas/policy-suggestions": { suggestions: [] }, [DIAGNOSE_PATH]: OK });
    renderIdea();
    await userEvent.type(screen.getByLabelText(/아이디어를 한두 문장으로/), "궤도 틀림이 반복됨.");
    await userEvent.click(screen.getByRole("button", { name: "네 칸으로 나누기" }));
    await userEvent.click(await screen.findByRole("button", { name: /상세 입력에 채우기/ }));
    expect(await screen.findByRole("dialog", { name: "정책 근거 추천" })).toBeInTheDocument();
    const card = await screen.findByTestId("problem-card");
    expect(within(card).getByTestId("card-line-function")).toHaveTextContent("궤도 틀림의 진행을 늦춘다");
    const sent = calls.filter((c) => c.url === DIAGNOSE_PATH);
    expect(sent).toHaveLength(1);
    expect(body(sent[0]!.init)).toEqual({ title_hint: "", ...FIELDS });
    expect(getIdea().cardSig).toBe(fourSignature(getIdea().request));
    // 디바운스가 지나도 같은 입력으로 다시 부르지 않는다
    await new Promise((r) => setTimeout(r, DIAGNOSE_DEBOUNCE_MS + 300));
    expect(calls.filter((c) => c.url === DIAGNOSE_PATH)).toHaveLength(1);
  }, 15_000);

  it("상세 입력 — 네 칸이 찬 뒤 입력이 멈추면 1회, 그동안 '문제 정리 중…' 한 줄", async () => {
    mockFetch({});
    const held = holdFetch(DIAGNOSE_PATH);
    startDetail();
    renderIdea();
    expect(screen.queryByTestId("problem-card-pending")).toBeNull();
    expect(await screen.findByTestId("problem-card-pending", undefined, WAIT)).toHaveTextContent("문제 정리 중…");
    // 화면은 막히지 않는다 — 입력 칸·다음 버튼이 그대로 쓸 수 있다
    expect(screen.getByLabelText(/현재 상황·문제/)).toBeEnabled();
    expect(screen.getByRole("button", { name: "다음: 유사과제 확인" })).toBeEnabled();
    await act(async () => held.release(OK));
    expect(await screen.findByTestId("problem-card")).toBeInTheDocument();
    expect(screen.queryByTestId("problem-card-pending")).toBeNull();
    expect(held.calls).toBe(1);
  }, 15_000);

  it("네 칸 중 빈 칸이 있으면 부르지 않는다", async () => {
    const { calls } = mockFetch({ [DIAGNOSE_PATH]: OK });
    updateIdea({ inputMode: "detail", request: { ...emptyRequest(), ...FIELDS, goal: " " } });
    renderIdea();
    await new Promise((r) => setTimeout(r, DIAGNOSE_DEBOUNCE_MS + 300));
    expect(calls).toHaveLength(0);
    expect(screen.queryByTestId("problem-card")).toBeNull();
  }, 15_000);

  it.each([
    ["꺼짐(status off)", () => OFF],
    ["실패(status failed)", () => ({ ...OFF, status: "failed", reason: "invalid", reason_label: "응답 형식 오류" })],
    ["경로 없음(404)", () => problem(404, "없음")],
    ["서버 오류(500)", () => problem(500, "오류")],
    [
      "네트워크 오류",
      () => {
        throw new TypeError("Failed to fetch");
      },
    ],
  ])("%s — 카드 영역 자체가 없고 알림도 없다, 같은 입력으로 다시 부르지 않는다", async (_name, respond) => {
    const { calls } = mockFetch({ [DIAGNOSE_PATH]: respond });
    startDetail();
    const { container } = renderIdea();
    await waitFor(() => expect(calls.filter((c) => c.url === DIAGNOSE_PATH)).toHaveLength(1), WAIT);
    await waitFor(() => expect(getIdea().cardSig).toBe(fourSignature(getIdea().request)));
    expect(screen.queryByTestId("problem-card")).toBeNull();
    expect(screen.queryByTestId("problem-card-pending")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(container.textContent).not.toMatch(/핵심 문제|문제 정리|응답 형식 오류/);
    expect(getIdea().problemCard).toBeNull();
  }, 15_000);

  it("네 칸이 바뀌면 '입력이 바뀌었습니다' 표시 → 멈춘 뒤 지금 카드를 previous 로 실어 다시 진단", async () => {
    const { calls } = mockFetch({ [DIAGNOSE_PATH]: (init?: RequestInit) => (body(init).previous ? { ...OK, lines: { ...OK.lines!, function: "다시 정리한 기능 문장" } } : OK) });
    startDetail({ problemCard: CARD, cardLines: OK.lines, cardSignals: OK.signal_labels, cardSig: fourSignature(FIELDS) });
    renderIdea();
    expect(screen.getByTestId("problem-card")).toBeInTheDocument();
    expect(screen.queryByTestId("problem-card-changed")).toBeNull();
    await userEvent.type(screen.getByLabelText(/해결 목표/), " (구간별)");
    expect(screen.getByTestId("problem-card-changed")).toHaveTextContent(CARD_INPUT_CHANGED);
    expect(await screen.findByText("다시 정리한 기능 문장", undefined, WAIT)).toBeInTheDocument();
    expect(screen.queryByTestId("problem-card-changed")).toBeNull();
    const sent = calls.filter((c) => c.url === DIAGNOSE_PATH);
    expect(sent).toHaveLength(1);
    expect(body(sent[0]!.init).previous).toEqual(CARD);
    expect(body(sent[0]!.init).goal).toBe(`${FIELDS.goal} (구간별)`);
  }, 15_000);
});

describe("① [다음] 과 카드", () => {
  it("카드가 있으면 들고 다니는 입력에 싣는다 — 유사과제 확인 요청 자체에는 싣지 않는다", async () => {
    const { calls } = mockFetch({ [DIAGNOSE_PATH]: OK, "/v1/precheck": PRE_PLAIN });
    startDetail({ problemCard: CARD, cardLines: OK.lines, cardSig: fourSignature(FIELDS) });
    renderIdea();
    await userEvent.click(screen.getByRole("button", { name: "다음: 유사과제 확인" }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/new/precheck"));
    const pre = calls.find((c) => c.url.startsWith("/v1/precheck"))!;
    expect(body(pre.init)).not.toHaveProperty("problem_card");
    expect(getIdea().request.problem_card).toEqual(CARD);
    expect(calls.some((c) => c.url === DIAGNOSE_PATH)).toBe(false);
  });

  it("진단이 아직 안 끝났으면 기다리지 않고 카드 없이 진행 — 진행 중 호출은 끊는다", async () => {
    mockFetch({ "/v1/ideas/structure": FULL, "/v1/ideas/policy-suggestions": { suggestions: [] }, "/v1/precheck": PRE_PLAIN });
    const held = holdFetch(DIAGNOSE_PATH); // 끝나지 않는 진단
    renderIdea();
    await userEvent.type(screen.getByLabelText(/아이디어를 한두 문장으로/), "궤도 틀림이 반복됨.");
    await userEvent.click(screen.getByRole("button", { name: "네 칸으로 나누기" }));
    await userEvent.click(await screen.findByRole("button", { name: /상세 입력에 채우기/ }));
    const d = await screen.findByRole("dialog", { name: "정책 근거 추천" });
    await waitFor(() => expect(held.calls).toBe(1));
    expect(screen.getByTestId("problem-card-pending")).toBeInTheDocument();
    await userEvent.click(within(d).getByRole("button", { name: "나중에 넣기" }));
    await userEvent.click(screen.getByRole("button", { name: "다음: 유사과제 확인" }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/new/precheck"));
    expect(held.signal?.aborted).toBe(true);
    expect(getIdea().request).not.toHaveProperty("problem_card");
    expect(getIdea().problemCard ?? null).toBeNull();
  }, 15_000);

  it("네 칸이 카드를 만든 때와 다르면(다시 정리하기 전) 그 카드는 싣지 않는다", () => {
    startDetail({ problemCard: CARD, cardLines: OK.lines, cardSig: fourSignature(FIELDS) });
    expect(usableCard()).toEqual(CARD);
    updateRequest({ goal: "다른 목표" });
    expect(usableCard()).toBeNull();
    updateIdea({ problemCard: null, cardSig: fourSignature(getIdea().request) });
    expect(usableCard()).toBeNull();
  });
});

describe("① 줄 고치기 → diagnose/edit", () => {
  const edited: Card = { ...CARD, function_ko: { ...CARD.function_ko, value: "궤도 틀림을 미리 알아낸다", origin: "user", ai_value: CARD.function_ko.value } };
  const EDIT_OUT: CardEditOut = { card: edited, lines: { ...OK.lines!, function: "궤도 틀림을 미리 알아낸다" }, reruns: ["derive", "analogy", "plans_stale"], plans_stale: true, recorded: true };

  it("[적용] → 요청 본문(네 칸·before·after·fields) → 응답의 카드·4줄로 갈아 끼운다. 과제안이 아직 없으면 표시 없음", async () => {
    const { calls } = mockFetch({ [DIAGNOSE_EDIT_PATH]: EDIT_OUT });
    startDetail({ problemCard: CARD, cardLines: OK.lines, cardSig: fourSignature(FIELDS) });
    renderIdea();
    await userEvent.click(screen.getByRole("button", { name: "기능 문장 고치기" }));
    const box = screen.getByLabelText("기능 문장");
    await userEvent.clear(box);
    await userEvent.type(box, "궤도 틀림을 미리 알아낸다");
    await userEvent.click(screen.getByRole("button", { name: "적용" }));
    const line = await screen.findByTestId("card-line-function");
    await waitFor(() => expect(within(line).getByTestId("card-by-user")).toBeInTheDocument());
    expect(line).toHaveTextContent("궤도 틀림을 미리 알아낸다");
    const sent = body(calls.find((c) => c.url === DIAGNOSE_EDIT_PATH)!.init) as { request: unknown; before: Card; after: Card; fields: string[] };
    expect(sent.request).toEqual({ title_hint: "", ...FIELDS });
    expect(sent.before).toEqual(CARD);
    expect(sent.after.function_ko.value).toBe("궤도 틀림을 미리 알아낸다");
    expect(sent.fields).toEqual(["function_ko"]);
    expect(getIdea().problemCard).toEqual(edited);
    expect(getIdea().plansStale ?? false).toBe(false);
    // 고친 뒤에도 같은 네 칸이면 다시 진단하지 않는다
    expect(calls.some((c) => c.url === DIAGNOSE_PATH)).toBe(false);
  });

  it("이미 받은 과제안이 있으면 plans_stale 표시를 켜고, 들고 다니는 입력의 카드도 새 카드로", async () => {
    mockFetch({ [DIAGNOSE_EDIT_PATH]: EDIT_OUT });
    startDetail({ problemCard: CARD, cardLines: OK.lines, cardSig: fourSignature(FIELDS) });
    updateIdea({ precheck: precheckFx as unknown as PrecheckOut, request: { ...getIdea().request, problem_card: CARD } });
    renderIdea();
    await userEvent.click(screen.getByRole("button", { name: "기능 문장 고치기" }));
    await userEvent.type(screen.getByLabelText("기능 문장"), " 그리고");
    await userEvent.click(screen.getByRole("button", { name: "적용" }));
    await waitFor(() => expect(getIdea().plansStale).toBe(true));
    expect(getIdea().request.problem_card).toEqual(edited);
  });

  it("plans_stale 이 아니면(원인만 고침) 표시하지 않는다", async () => {
    mockFetch({ [DIAGNOSE_EDIT_PATH]: { ...EDIT_OUT, reruns: ["checks", "clarify"], plans_stale: false } });
    startDetail({ problemCard: CARD, cardLines: OK.lines, cardSig: fourSignature(FIELDS) });
    updateIdea({ precheck: precheckFx as unknown as PrecheckOut });
    renderIdea();
    await userEvent.click(screen.getByRole("button", { name: "원인 고치기" }));
    await userEvent.type(screen.getByLabelText("원인"), " 때문");
    await userEvent.click(screen.getByRole("button", { name: "적용" }));
    await waitFor(() => expect(getIdea().problemCard).toEqual(edited));
    expect(getIdea().plansStale ?? false).toBe(false);
  });
});

describe("② 문제 정의가 바뀌었습니다", () => {
  const routes = (calls: { n: number }) => ({
    "/v1/precheck/comparison": { notice: "", comparison: null },
    "/v1/precheck/judgment": precheckFx,
    "/v1/precheck/recommendations": () => {
      calls.n += 1;
      return precheckFx;
    },
  });

  it("한 줄과 [과제안 다시 만들기] — 자동으로 다시 만들지 않고, 누르면 카드를 실어 다시 받고 표시를 지운다", async () => {
    const made = { n: 0 };
    const { calls } = mockFetch(routes(made));
    updateIdea({ precheck: precheckFx as unknown as PrecheckOut, request: { ...emptyRequest(), ...FIELDS, problem_card: CARD }, problemCard: CARD, plansStale: true });
    renderWithProviders(<Precheck />, { route: "/new/precheck" });
    const note = await screen.findByTestId("plans-stale-note");
    expect(note).toHaveTextContent(PLANS_STALE_NOTE);
    await new Promise((r) => setTimeout(r, 300));
    expect(made.n).toBe(0);
    // 카드는 ② 판정·비교표 요청에 실리지 않는다
    for (const c of calls.filter((x) => !x.url.includes("/recommendations"))) expect(body(c.init)).not.toHaveProperty("problem_card");
    await userEvent.click(within(note).getByRole("button", { name: "과제안 다시 만들기" }));
    await waitFor(() => expect(made.n).toBe(1));
    expect(body(calls.find((c) => c.url === "/v1/precheck/recommendations")!.init).problem_card).toEqual(CARD);
    await waitFor(() => expect(screen.queryByTestId("plans-stale-note")).toBeNull());
    expect(getIdea().plansStale).toBe(false);
  });

  it("표시가 없으면(카드 없음·고치지 않음) 한 줄도 없다 — 종전 화면 그대로, 요청에 problem_card 칸이 없다", async () => {
    const made = { n: 0 };
    const { calls } = mockFetch(routes(made));
    updateIdea({ precheck: precheckFx as unknown as PrecheckOut, request: { ...emptyRequest(), ...FIELDS } });
    renderWithProviders(<Precheck />, { route: "/new/precheck" });
    await screen.findByRole("heading", { name: /유사과제 확인/ });
    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    expect(screen.queryByTestId("plans-stale-note")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "과제안 다시 만들기" }));
    await waitFor(() => expect(made.n).toBe(1));
    for (const c of calls) expect(body(c.init)).not.toHaveProperty("problem_card");
  });

  it("[다음] 은 카드를 다음 단계 입력에 그대로 둔다", async () => {
    mockFetch(routes({ n: 0 }));
    updateIdea({ precheck: { ...precheckFx, blocking: false, alerts: [] } as unknown as PrecheckOut, request: { ...emptyRequest(), ...FIELDS, problem_card: CARD } });
    renderWithProviders(
      <Routes>
        <Route path="/new/precheck" element={<Precheck />} />
        <Route path="*" element={<Where />} />
      </Routes>,
      { route: "/new/precheck" },
    );
    await userEvent.click(await screen.findByRole("button", { name: /다음: 선행연구 브리핑/ }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/new/brief"));
    expect(getIdea().request.problem_card).toEqual(CARD);
  });
});

describe("② 과제명의 발명 원리", () => {
  const novel = (principles?: { number: number; name: string }[]): NovelRecommendations =>
    ({
      id: "rec-novel",
      mode: "novel",
      discarded: [],
      coverage: { searched: ["own"], searched_labels: ["사내 과제"], live: false, unavailable: [], note: "" },
      analogies: [],
      recommendations: [
        {
          index: 0,
          approach: "다른 분야 방식 옮기기",
          summary: "요약",
          first_step: "첫 단계",
          stages: [],
          maturity: "실증 필요",
          evidence: [],
          refs: [],
          barriers: [{ type: "비용", statement: "장비 비용", basis: { level: "추정", doc_ids: [] }, check: "견적 받기" }],
          titles: [{ title: "저비용 검측 체계 연구", resolves: [0], resolves_types: ["비용"], reason: "", ...(principles ? { principles } : {}) }],
        },
      ],
    }) as unknown as NovelRecommendations;
  const render = (rec: NovelRecommendations) =>
    renderWithProviders(
      <PlanCards rec={rec} waiting={{ pending: false, elapsed: 0, cancelled: false, onCancel: vi.fn() }} chosenIndex={null} stale={false} onPick={vi.fn()} onKeepOriginal={vi.fn()} onWrite={vi.fn()} onRegenerate={vi.fn()} />,
    );

  it("principles 가 있으면 '발명 원리 n. 이름' 배지, 없거나 비면 종전과 같다", () => {
    const a = render(novel([{ number: 10, name: "사전 조치" }, { number: 35, name: "속성 변환" }]));
    expect(screen.getAllByTestId("title-principle").map((b) => b.textContent)).toEqual(["발명 원리 10. 사전 조치", "발명 원리 35. 속성 변환"]);
    a.unmount();
    const b = render(novel([]));
    expect(screen.queryByTestId("title-principle")).toBeNull();
    b.unmount();
    render(novel());
    expect(screen.queryByTestId("title-principle")).toBeNull();
    expect(screen.getByTestId("title-resolves")).toHaveTextContent("해소: 비용");
  });
});

describe("화면 상태 호환", () => {
  afterEach(() => sessionStorage.clear());

  it("옛 화면 상태(카드 칸 없음)를 읽어도 깨지지 않고 카드 없이 시작한다", async () => {
    sessionStorage.setItem("rra-idea", JSON.stringify({ inputMode: "detail", request: { ...FIELDS }, policyDeferred: true }));
    vi.resetModules();
    const fresh = await import("@/features/idea/store");
    const s = fresh.getIdea();
    expect(s.problemCard ?? null).toBeNull();
    expect(s.cardSig ?? null).toBeNull();
    expect(s.plansStale ?? false).toBe(false);
    expect(s.request.goal).toBe(FIELDS.goal);
    fresh.resetIdea();
  });

  it("카드가 든 상태는 새로고침에 견딘다 / 새 유사과제 확인 결과가 오면 '문제 정의가 바뀌었습니다' 표시는 지운다", async () => {
    sessionStorage.setItem("rra-idea", JSON.stringify({ request: { ...FIELDS }, problemCard: CARD, cardLines: OK.lines, cardSig: fourSignature(FIELDS), plansStale: true }));
    vi.resetModules();
    const fresh = await import("@/features/idea/store");
    expect(fresh.getIdea().problemCard).toEqual(CARD);
    expect(fresh.getIdea().plansStale).toBe(true);
    fresh.updateIdea({ precheck: precheckFx as unknown as PrecheckOut });
    expect(fresh.getIdea().plansStale).toBe(false);
    expect(fresh.getIdea().problemCard).toEqual(CARD);
    fresh.resetIdea();
    expect(fresh.getIdea().problemCard ?? null).toBeNull();
  });

  it("네 칸 서명 — 한 칸이라도 비면 null, 앞뒤 공백 무시 / withoutCard 는 카드만 뗀다", () => {
    expect(fourSignature({ ...FIELDS, goal: "" })).toBeNull();
    expect(fourSignature({ ...FIELDS, goal: ` ${FIELDS.goal} ` })).toBe(fourSignature(FIELDS));
    expect(fourSignature({ ...FIELDS, goal: "다른" })).not.toBe(fourSignature(FIELDS));
    expect(withoutCard({ ...FIELDS, problem_card: CARD })).toEqual(FIELDS);
    expect(withoutCard(FIELDS as typeof FIELDS & { problem_card?: unknown })).toEqual(FIELDS);
  });
});
