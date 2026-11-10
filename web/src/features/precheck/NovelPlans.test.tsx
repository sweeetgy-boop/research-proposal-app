/** ② 새 과제안 갈래 (ADR 0057, 레인 C) — 갈래별 제목·coverage 문구(live·unavailable)·다른 분야 사례 링크·배지·장벽 배지
 *  (근거 있음 / 추정 + 확인 방법)·과제명 "해소:" 배지·[이 과제명으로 진행] → 가제·novel 에서 더 만들기 숨김·novelty_reverted 한 줄·
 *  화면에 내부 번호·내부 코드 없음. 응답 모양은 api/types-novel.ts 그대로(백엔드 없음). */
import * as React from "react";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations, mockFetch, renderWithProviders } from "@/test/utils";
import { clearSession } from "@/auth/session";
import { getIdea, resetIdea, updateIdea } from "@/features/idea/store";
import { focusRelatedResearch, RELATED_RESEARCH_HEADING_ID } from "@/features/idea/relatedResearchFocus";
import { emptyRequest } from "@/lib/validation";
import Precheck from "@/routes/Precheck";
import type { PlanRecommendations, PrecheckAlert, PrecheckOut } from "@/api/types";
import type { AnalogyReport, AnyRecommendations, DifferentiateRecommendations, NovelRecommendation, NovelRecommendations } from "@/api/types-novel";
import { NOVELTY_REVERTED_NOTE, PLAN_HEADINGS, PlanCards, type NovelTitleProps } from "./PlanCards";
import { SummaryBar } from "./SummaryBar";

afterEach(() => {
  vi.unstubAllGlobals();
  clearSession();
  resetIdea();
});

const INTERNAL_ID = /\b(own|alio|ntis|scienceon|openalex|korail_web|g2b|kipris|kipris_kr):[\w-]+/;
/** 화면에 나가면 안 되는 열거값·내부 코드 */
const INTERNAL_CODES = /ip_blocked|no_key|timeout|\bnovel\b|differentiate|resolves|doc_id/;

const BASE = {
  skipped_reason: null,
  no_recommendation_reason: null,
  provider: "gemini",
  model: "argon",
  fallback_local: false,
  transfer: { public_doc_ids: [], internal_doc_ids: [], excluded_doc_ids: [], calls: 1 },
  discarded: [],
};

const novelCard = (index: number, over: Partial<NovelRecommendation> = {}): NovelRecommendation => ({
  index,
  approach: index === 0 ? "물류 창고 드론 재고 조사 방식을 역사 설비 점검에 옮기기" : "항만 크레인 예지보전 모델을 차량 기지에 적용",
  summary: "○ 역 구내 설비를 드론으로 점검",
  first_step: "○ 시범 역 1곳 선정",
  stages: [
    { stage: "기획", text: "점검 대상 설비 목록화" },
    { stage: "시범", text: "한 역에서 3개월 시범" },
    { stage: "확대", text: "권역 확대" },
  ],
  maturity: index === 0 ? "실증 필요" : "즉시 적용",
  evidence: ["openalex:W1"],
  refs: [
    { doc_id: "openalex:W1", title: "Warehouse drone inventory (가짜)", source: "openalex", source_label: "OpenAlex 논문", url: "https://openalex.org/W1" },
    { doc_id: "scienceon:A2", title: "드론 비행 규정 검토 (가짜)", source: "scienceon", source_label: "ScienceON", url: null },
  ],
  barriers: [
    { type: "규제", statement: "역 구내 드론 비행 승인 필요", basis: { level: "근거 있음", doc_ids: ["scienceon:A2"] }, check: "" },
    { type: "비용", statement: "장비 구입 비용 부담", basis: { level: "추정", doc_ids: [] }, check: "유사 장비 견적 2곳 받아 보기" },
    { type: "운영", statement: "점검 인력 교육", basis: { level: "추정", doc_ids: [] }, check: "현장 담당자 면담" },
  ],
  titles: [
    { title: "역 구내 드론 점검 승인·저비용 운용 체계 연구", resolves: [0, 1], resolves_types: ["규제", "비용"], reason: "승인 절차와 비용을 함께 푼다" },
    { title: "드론 점검 인력 운영 모델 연구", resolves: [2], resolves_types: ["운영"], reason: "교육 부담을 줄인다" },
  ],
  ...over,
});

const novel = (over: Partial<NovelRecommendations> = {}): NovelRecommendations => ({
  id: "rec-novel",
  mode: "novel",
  ...BASE,
  coverage: {
    searched: ["own", "scienceon", "openalex"],
    searched_labels: ["사내 과제", "ScienceON", "OpenAlex"],
    live: true,
    unavailable: [{ source: "ntis", label: "NTIS", status: "ip_blocked", status_label: "서버 IP 등록 필요로 확인 못 함" }],
    note: "저장 자료와 실시간 검색 범위 안에서 기존 과제 없음",
  },
  analogies: [
    {
      doc_id: "openalex:W9",
      title: "Drone-based inventory in logistics (가짜)",
      source: "openalex",
      source_label: "OpenAlex 논문",
      domain_label: "물류",
      why_relevant: "점검 자동화라는 같은 문제를 다룸",
      url: "https://openalex.org/W9",
      year: 2024,
      live: true,
    },
    {
      doc_id: "scienceon:X1",
      title: "항만 크레인 예지보전 (가짜)",
      source: "scienceon",
      source_label: "ScienceON",
      domain_label: "항만",
      why_relevant: "설비 고장 예측",
      url: "javascript:alert(1)",
      year: null,
      live: false,
    },
  ],
  recommendations: [novelCard(0), novelCard(1)],
  ...over,
});

const diffCard = {
  index: 0,
  title: "차별화 과제안 가",
  summary: "요약",
  goal: "목표",
  method: "방법",
  scope: "범위",
  differentiation: "차이",
  reasons: [],
  build_on: "",
  risks: "",
  compared_with: [],
  evidence: [],
  overlap_warning: [],
  refs: [],
};
const diff = (over: Partial<DifferentiateRecommendations> = {}): DifferentiateRecommendations =>
  ({ id: "rec-diff", ...BASE, recommendations: [diffCard], ...over }) as DifferentiateRecommendations;

const waiting = { pending: false, elapsed: 0, cancelled: false, onCancel: vi.fn() };

function renderCards(rec: AnyRecommendations, novelTitle?: NovelTitleProps, extra: Partial<React.ComponentProps<typeof PlanCards>> = {}) {
  return renderWithProviders(
    <PlanCards
      rec={rec}
      waiting={waiting}
      chosenIndex={null}
      stale={false}
      onPick={vi.fn()}
      onKeepOriginal={vi.fn()}
      onWrite={vi.fn()}
      onRegenerate={vi.fn()}
      novelTitle={novelTitle}
      {...extra}
    />,
  );
}

/** 가제 칸 상태를 들고 있는 감싸개 */
function NovelHarness({ rec, initial = "" }: { rec: NovelRecommendations; initial?: string }) {
  const [title, setTitle] = React.useState(initial);
  return (
    <PlanCards
      rec={rec}
      waiting={waiting}
      chosenIndex={null}
      stale={false}
      onPick={vi.fn()}
      onKeepOriginal={vi.fn()}
      onWrite={vi.fn()}
      onRegenerate={vi.fn()}
      novelTitle={{ titleHint: title, onUseTitle: setTitle, onTitleHintChange: setTitle }}
    />
  );
}

describe("② 과제안 갈래별 제목", () => {
  it("mode 없음 → 차별화, differentiate → 차별화, novel → 새 과제안", () => {
    const { unmount } = renderCards(diff());
    expect(screen.getByRole("heading", { level: 2, name: PLAN_HEADINGS.differentiate })).toBeInTheDocument();
    unmount();
    const r2 = renderCards(diff({ mode: "differentiate" }));
    expect(screen.getByRole("heading", { level: 2, name: "차별화 과제안 고르기" })).toBeInTheDocument();
    r2.unmount();
    renderCards(novel());
    expect(screen.getByRole("heading", { level: 2, name: "새 과제안 고르기 (신규 영역)" })).toBeInTheDocument();
    expect(screen.queryByText("차별화 과제안 고르기")).toBeNull();
    // [과제안 다시 만들기] 는 두 갈래 모두
    expect(screen.getByRole("button", { name: "과제안 다시 만들기" })).toBeInTheDocument();
  });
});

describe("② 새 과제안 화면", () => {
  it("coverage — 실시간 검색 함, 확인한 자료원, 확인 못 한 자료원은 작은 글씨 한국어 설명 (axe 0, 내부 번호·코드 없음)", async () => {
    const { container } = renderCards(novel(), { titleHint: "", onUseTitle: vi.fn(), onTitleHintChange: vi.fn() });
    const cov = screen.getByTestId("novelty-coverage");
    expect(cov).toHaveTextContent("저장 자료와 실시간 검색 범위 안에서 기존 과제가 없습니다");
    expect(cov).toHaveTextContent("확인한 자료원: 사내 과제·ScienceON·OpenAlex");
    expect(screen.getByTestId("novel-unavailable")).toHaveTextContent("NTIS: 서버 IP 등록 필요로 확인 못 함");
    expect(container.textContent).not.toMatch(INTERNAL_ID);
    expect(container.textContent).not.toMatch(INTERNAL_CODES);
    await expectNoA11yViolations(container);
  });

  it("coverage — 실시간 검색을 못 했으면 '저장 자료 범위 안에서…', 확인 못 한 자료원이 없으면 그 줄 없음", () => {
    renderCards(novel({ coverage: { searched: ["own"], searched_labels: ["사내 과제"], live: false, unavailable: [], note: "" } }));
    const cov = screen.getByTestId("novelty-coverage");
    expect(cov).toHaveTextContent("저장 자료 범위 안에서 기존 과제가 없습니다");
    expect(cov).not.toHaveTextContent("실시간 검색");
    expect(screen.queryByTestId("novel-unavailable")).toBeNull();
  });

  it("다른 분야 사례 — 원문 링크는 새 창·noopener, http(s) 아닌 주소는 링크로 만들지 않음, '참고' 배지·분야·이유", () => {
    renderCards(novel());
    const list = screen.getByTestId("novel-analogies");
    expect(within(list).getByRole("heading", { name: "다른 분야 사례" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "다른 분야 사례" })).toBe(list);
    const items = within(list).getAllByTestId("novel-analogy");
    expect(items).toHaveLength(2);
    const link = within(items[0]!).getByRole("link", { name: /Drone-based inventory in logistics/ });
    expect(link).toHaveAttribute("href", "https://openalex.org/W9");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toMatch(/noopener/);
    expect(within(items[0]!).getByText("참고")).toBeInTheDocument();
    expect(items[0]).toHaveTextContent("물류 · OpenAlex 논문 · 2024");
    expect(items[0]).toHaveTextContent("점검 자동화라는 같은 문제를 다룸");
    expect(within(items[1]!).queryByRole("link")).toBeNull();
    expect(items[1]).toHaveTextContent("항만 크레인 예지보전 (가짜)");
    expect(within(items[1]!).getByText("참고")).toBeInTheDocument();
  });

  it("다른 분야 사례가 없으면 목록을 숨긴다", () => {
    renderCards(novel({ analogies: [] }));
    expect(screen.queryByTestId("novel-analogies")).toBeNull();
    expect(screen.queryByText("다른 분야 사례")).toBeNull();
  });

  describe("검색 범위 보고(analogy_report)", () => {
    const report = (over: Partial<AnalogyReport> = {}): AnalogyReport => ({
      kind: "other_field",
      heading: "다른 분야 사례",
      description: "철도 밖에서 비슷한 문제를 다룬 자료입니다(가짜 설명).",
      count: 2,
      dropped_weak: 0,
      sources_total: 4,
      sources_checked: 4,
      checked_labels: ["ScienceON", "OpenAlex", "KIPRIS", "NTIS"],
      unavailable: [],
      partial: false,
      languages: ["한국어", "영어"],
      scope_text: "자료원 4곳 중 4곳 확인 — ScienceON·OpenAlex·KIPRIS·NTIS",
      empty_text: "찾지 못했습니다(검색 범위: 한국어·영어, 자료원 4곳)",
      ...over,
    });
    const five = Array.from({ length: 5 }, (_, i) => ({ ...novel().analogies[0]!, doc_id: `openalex:W${i}`, title: `사례 ${i + 1} (가짜)` }));

    it("보고가 없으면 종전과 같다 — 제목·설명 그대로, 범위 줄·배지·빈 문구 없음, 0건이면 구획 없음", () => {
      const { unmount } = renderCards(novel());
      const list = screen.getByTestId("novel-analogies");
      expect(within(list).getByRole("heading", { name: "다른 분야 사례" })).toBeInTheDocument();
      expect(list).toHaveTextContent("철도 밖에서 비슷한 문제를 다룬 자료입니다. 과제안의 참고일 뿐 근거로 그대로 쓰지 마십시오.");
      for (const id of ["analogy-scope", "analogy-partial", "analogy-empty", "analogy-add-reference", "analogy-dropped"]) {
        expect(screen.queryByTestId(id)).toBeNull();
      }
      unmount();
      renderCards(novel({ analogies: [], analogy_report: null }), undefined, { onFindReferences: vi.fn() });
      expect(screen.queryByTestId("novel-analogies")).toBeNull();
    });

    it("대상이 철도 시설이면 제목 '관련 선행 자료' 와 서버 설명을 보인다", () => {
      renderCards(novel({ analogy_report: report({ kind: "related", heading: "관련 선행 자료", description: "대상이 철도 시설이라 철도 자료를 함께 보입니다." }) }));
      const list = screen.getByTestId("novel-analogies");
      expect(within(list).getByRole("heading", { level: 3, name: "관련 선행 자료" })).toBeInTheDocument();
      expect(screen.getByRole("region", { name: "관련 선행 자료" })).toBe(list);
      expect(list).toHaveTextContent("대상이 철도 시설이라 철도 자료를 함께 보입니다.");
      expect(screen.queryByText("다른 분야 사례")).toBeNull();
      expect(list).not.toHaveTextContent("철도 밖에서 비슷한 문제를 다룬 자료입니다. 과제안의 참고일 뿐");
      expect(list.textContent).not.toMatch(/other_field|related/);
    });

    it("3건·일부만 확인 — 범위 줄과 '일부만 확인' 배지 (axe 0)", async () => {
      const scope = "자료원 4곳 중 3곳 확인 — ScienceON·OpenAlex·KIPRIS. 확인 못 함: NTIS(서버 IP 등록 필요)";
      const { container } = renderCards(
        novel({
          analogies: five.slice(0, 3),
          analogy_report: report({
            count: 3,
            partial: true,
            sources_checked: 3,
            unavailable: [{ source: "ntis", label: "NTIS", status: "ip_blocked", status_label: "서버 IP 등록 필요" }],
            scope_text: scope,
          }),
        }),
      );
      expect(screen.getByTestId("analogy-scope")).toHaveTextContent(scope);
      expect(screen.getByTestId("analogy-partial")).toHaveTextContent("일부만 확인");
      expect(screen.getAllByTestId("novel-analogy")).toHaveLength(3);
      expect(screen.queryByTestId("analogy-empty")).toBeNull();
      expect(screen.getByTestId("novel-analogies").textContent).not.toMatch(INTERNAL_CODES);
      await expectNoA11yViolations(container);
    });

    it("5건 미만이면 전부 확인했어도 범위 줄을 보인다(배지는 없음)", () => {
      renderCards(novel({ analogy_report: report({ count: 2 }) }));
      expect(screen.getByTestId("analogy-scope")).toBeInTheDocument();
      expect(screen.queryByTestId("analogy-partial")).toBeNull();
    });

    it("5건이 찼고 전부 확인했으면 범위 줄·배지가 없다", () => {
      renderCards(novel({ analogies: five, analogy_report: report({ count: 5 }) }));
      expect(screen.getAllByTestId("novel-analogy")).toHaveLength(5);
      expect(screen.queryByTestId("analogy-scope")).toBeNull();
      expect(screen.queryByTestId("analogy-partial")).toBeNull();
      expect(screen.queryByTestId("analogy-dropped")).toBeNull();
    });

    it("0건 — 구획을 그리고 빈 문구·[아는 자료 직접 추가]·안내 줄, 버튼은 관련 연구로 포커스를 옮긴다", async () => {
      const onFind = vi.fn(focusRelatedResearch);
      const { container } = renderWithProviders(
        <>
          <h2 id={RELATED_RESEARCH_HEADING_ID} tabIndex={-1}>
            관련 연구 3건
          </h2>
          <PlanCards
            rec={novel({ analogies: [], analogy_report: report({ count: 0 }) })}
            waiting={waiting}
            chosenIndex={null}
            stale={false}
            onPick={vi.fn()}
            onKeepOriginal={vi.fn()}
            onWrite={vi.fn()}
            onRegenerate={vi.fn()}
            onFindReferences={onFind}
          />
        </>,
      );
      const list = screen.getByTestId("novel-analogies");
      expect(within(list).getByRole("heading", { name: "다른 분야 사례" })).toBeInTheDocument();
      expect(screen.getByTestId("analogy-empty")).toHaveTextContent("찾지 못했습니다(검색 범위: 한국어·영어, 자료원 4곳)");
      expect(list).toHaveTextContent("관련 연구에서 [차별화에 참고]로 고르면 다음 과제안에 반영됩니다.");
      expect(screen.queryByTestId("novel-analogy")).toBeNull();
      // 전부 확인한 0건은 빈 문구가 범위를 말하므로 범위 줄·배지를 따로 내지 않는다
      expect(screen.queryByTestId("analogy-scope")).toBeNull();
      expect(screen.queryByTestId("analogy-partial")).toBeNull();
      await userEvent.click(screen.getByRole("button", { name: "아는 자료 직접 추가" }));
      expect(onFind).toHaveBeenCalledTimes(1);
      expect(screen.getByRole("heading", { name: "관련 연구 3건" })).toHaveFocus();
      await expectNoA11yViolations(container);
    });

    it("0건·일부만 확인 — 빈 문구에 더해 배지와 범위 줄, 추천 0건 화면에서도 보인다", () => {
      renderCards(
        novel({
          analogies: [],
          recommendations: [],
          analogy_report: report({ count: 0, partial: true, scope_text: "자료원 4곳 중 2곳 확인 — ScienceON·OpenAlex" }),
        }),
        undefined,
        { onFindReferences: vi.fn() },
      );
      expect(screen.getByTestId("analogy-empty")).toBeInTheDocument();
      expect(screen.getByTestId("analogy-partial")).toHaveTextContent("일부만 확인");
      expect(screen.getByTestId("analogy-scope")).toHaveTextContent("자료원 4곳 중 2곳 확인 — ScienceON·OpenAlex");
      expect(screen.getByTestId("analogy-add-reference")).toBeInTheDocument();
    });

    it("약해서 뺀 자료가 있으면 건수를 작은 글로 알린다", () => {
      renderCards(novel({ analogy_report: report({ dropped_weak: 3 }) }));
      expect(screen.getByTestId("analogy-dropped")).toHaveTextContent("관련이 약한 자료 3건은 뺐습니다.");
    });
  });

  it("안 카드 — 접근 방식·요약·성숙도 배지·단계(기획 → 시범 → 확대)·첫 단계·근거(제목·자료원)", () => {
    renderCards(novel());
    const cards = screen.getAllByTestId("novel-card");
    expect(cards).toHaveLength(2);
    const c = cards[0]!;
    expect(c).toHaveTextContent("물류 창고 드론 재고 조사 방식을 역사 설비 점검에 옮기기");
    expect(within(c).getByTestId("novel-maturity")).toHaveTextContent("실증 필요");
    expect(within(cards[1]!).getByTestId("novel-maturity")).toHaveTextContent("즉시 적용");
    const stages = within(within(c).getByTestId("novel-stages")).getAllByRole("listitem");
    expect(stages.map((s) => s.textContent)).toEqual(["기획 점검 대상 설비 목록화", "→시범 한 역에서 3개월 시범", "→확대 권역 확대"]);
    expect(c).toHaveTextContent("○ 시범 역 1곳 선정");
    const refs = within(c).getByTestId("novel-refs");
    expect(refs).toHaveTextContent(/Warehouse drone inventory \(가짜\)(\(새 창\))? · OpenAlex 논문/);
    expect(refs).toHaveTextContent("드론 비행 규정 검토 (가짜) · ScienceON");
    expect(within(refs).getByRole("link", { name: /Warehouse drone inventory/ })).toHaveAttribute("rel", "noopener noreferrer");
    expect(c.textContent).not.toMatch(INTERNAL_ID);
  });

  it("장벽 — 유형 배지 + '근거 있음'(근거 제목) / '추정 — 확인 방법: …'", () => {
    renderCards(novel());
    const barriers = within(screen.getAllByTestId("novel-card")[0]!).getAllByTestId("novel-barrier");
    expect(barriers).toHaveLength(3);
    expect(within(barriers[0]!).getByText("규제")).toBeInTheDocument();
    expect(within(barriers[0]!).getByText("근거 있음")).toBeInTheDocument();
    expect(barriers[0]).toHaveTextContent("근거: 드론 비행 규정 검토 (가짜) · ScienceON");
    expect(within(barriers[1]!).getByText("비용")).toBeInTheDocument();
    expect(within(barriers[1]!).getByText("추정")).toBeInTheDocument();
    expect(barriers[1]).toHaveTextContent("— 확인 방법: 유사 장비 견적 2곳 받아 보기");
    expect(within(barriers[2]!).getByText("운영")).toBeInTheDocument();
    expect(barriers[2]).toHaveTextContent("확인 방법: 현장 담당자 면담");
    // e2e 용 testid — 유형 배지·근거 배지
    expect(barriers.map((b) => within(b).getByTestId("barrier-type").textContent)).toEqual(["규제", "비용", "운영"]);
    expect(barriers.map((b) => within(b).getByTestId("barrier-basis").textContent)).toEqual(["근거 있음", "추정", "추정"]);
  });

  it("과제명 — '해소: 규제·비용' 배지·이유, [이 과제명으로 진행] → 가제 칸(수정 가능), 같은 값이면 비활성 '반영됨' (axe 0)", async () => {
    const { container } = renderWithProviders(<NovelHarness rec={novel()} />);
    const titles = within(screen.getAllByTestId("novel-card")[0]!).getAllByTestId("novel-title");
    expect(titles).toHaveLength(2);
    expect(within(titles[0]!).getByTestId("title-resolves")).toHaveTextContent("해소: 규제·비용");
    expect(within(titles[1]!).getByTestId("title-resolves")).toHaveTextContent("해소: 운영");
    expect(titles[0]).toHaveTextContent("승인 절차와 비용을 함께 푼다");

    const input = screen.getByRole("textbox", { name: "과제명(가제)" });
    expect(input).toHaveValue("");
    await userEvent.click(within(titles[0]!).getByRole("button", { name: "이 과제명으로 진행" }));
    expect(input).toHaveValue("역 구내 드론 점검 승인·저비용 운용 체계 연구");
    const used = within(titles[0]!).getByRole("button", { name: "반영됨" });
    expect(used).toBeDisabled();
    expect(within(titles[1]!).getByRole("button", { name: "이 과제명으로 진행" })).toBeEnabled();

    // 고칠 수 있다 — 고치면 다시 [이 과제명으로 진행] 이 켜진다
    await userEvent.type(input, " 2단계");
    expect(input).toHaveValue("역 구내 드론 점검 승인·저비용 운용 체계 연구 2단계");
    expect(within(titles[0]!).getByRole("button", { name: "이 과제명으로 진행" })).toBeEnabled();
    await expectNoA11yViolations(container);
  });

  it("novel 은 [이 안으로 진행](카드 적용)이 없다 — [원래 아이디어 유지]·[직접 작성] 은 그대로", () => {
    renderCards(novel());
    expect(screen.queryByRole("button", { name: "이 안으로 진행" })).toBeNull();
    expect(screen.getByRole("button", { name: "원래 아이디어 유지" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "직접 작성" })).toBeInTheDocument();
  });

  it("추천 0건 + hint=reference — 참고 논문 안내는 차별화와 같고, coverage 는 그대로 보인다", () => {
    renderCards(novel({ recommendations: [], no_recommendation_reason: "검증을 통과한 안이 없습니다", hint: "reference", retry_used: true }), undefined, {
      referenceCount: 0,
    });
    expect(screen.getByRole("heading", { level: 2, name: "새 과제안 고르기 (신규 영역)" })).toBeInTheDocument();
    expect(screen.getByTestId("novelty-coverage")).toBeInTheDocument();
    expect(screen.getByTestId("plan-reference-hint")).toHaveTextContent("참고 논문을 골라 [과제안 다시 만들기]");
    expect(screen.getByText("검증을 통과한 안이 없습니다")).toBeInTheDocument();
    expect(screen.getByTestId("plan-retry-note")).toHaveTextContent("한 번 더 받았습니다");
    expect(screen.queryAllByTestId("novel-card")).toHaveLength(0);
  });
});

describe("② novelty_reverted", () => {
  it("차별화로 되돌렸으면 과제안 위에 한 줄, 아니면 없음", () => {
    const { unmount } = renderCards(diff({ mode: "differentiate", novelty_reverted: true, novelty_alert_ids: ["own:9"] }));
    expect(screen.getByTestId("novelty-reverted-note")).toHaveTextContent(NOVELTY_REVERTED_NOTE);
    expect(screen.getByTestId("novelty-reverted-note")).toHaveTextContent("넓은 검색에서 비슷한 과제를 새로 찾아 차별화 과제안으로 바꿨습니다");
    expect(screen.getByRole("heading", { level: 2, name: "차별화 과제안 고르기" })).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(INTERNAL_ID);
    unmount();
    renderCards(diff({ mode: "differentiate", novelty_reverted: false }));
    expect(screen.queryByTestId("novelty-reverted-note")).toBeNull();
  });
});

describe("② 선택 요약 막대 — 더 만들기", () => {
  it("showMore=false 면 [차별화 과제안 더 만들기] 가 없다", () => {
    const props = {
      similar: 0,
      unrelated: 2,
      stale: false,
      applied: true,
      applying: false,
      onApply: vi.fn(),
      onMore: vi.fn(),
      moreDisabled: false,
      morePending: false,
      moreElapsed: 0,
      onCancelMore: vi.fn(),
    };
    const { unmount } = renderWithProviders(<SummaryBar {...props} />);
    expect(screen.getByRole("button", { name: "차별화 과제안 더 만들기" })).toBeInTheDocument();
    unmount();
    renderWithProviders(<SummaryBar {...props} showMore={false} />);
    expect(screen.queryByRole("button", { name: "차별화 과제안 더 만들기" })).toBeNull();
    expect(screen.getByRole("button", { name: "선택 적용" })).toBeInTheDocument();
  });
});

// ── ② 화면 전체 ──
const ALERT: PrecheckAlert = {
  doc_id: "own:1",
  title: "역사 조류 퇴치 과제",
  tier: "own",
  similarity: 0.82,
  blocking: false,
  basis: "summary",
  keywords: ["조류"],
  status: null,
  own_detail: "institute",
  tier_label: "사내(철도연구원)",
  relevance: "mid",
  relevance_label: "보통",
  source_label: "사내 과제 현황",
  judgment: "different",
  judgment_label: "다르다",
  judged_by: "argon",
  merged_ids: [],
};
const JUDGED = { status: "ai" as const, judged_by: "argon", judged_by_label: "Argon", message: "Argon 이 판정했습니다.", retry_available: false, candidates: 1, provider: "gemini", model: "argon", calls: 1 };
const COMPARISON = {
  notice: "",
  comparison: {
    aspects: [{ key: "objective", label: "연구목표" }],
    proposal: { doc_id: null, title: "가제", tier: null, similarity: null, blocking: false, basis: null, title_only: false, cells: { objective: "목표" } },
    projects: [],
    empty_reason: "유사한 과제를 고르면 비교표가 만들어집니다",
  },
};
const request = { ...emptyRequest(), current_state: "a", root_cause: "b", limitation: "c", goal: "목표", title_hint: "" };

function startWith(rec: AnyRecommendations) {
  updateIdea({
    precheck: { notice: "", blocking: false, alerts: [ALERT], judgment: JUDGED, recommendations: rec as unknown as PlanRecommendations } as unknown as PrecheckOut,
    request,
  });
}

describe("② 화면 — 새 과제안 갈래", () => {
  it("novel 응답 — 제목·더 만들기 숨김·[이 과제명으로 진행] → 가제(idea store)·수정, 카드 적용 요청 없음, 내부 번호 없음 (axe 0)", async () => {
    const { calls } = mockFetch({ "/v1/precheck/comparison": COMPARISON });
    startWith(novel());
    const { container } = renderWithProviders(<Precheck />, { route: "/new/precheck" });
    expect(screen.getByRole("heading", { level: 2, name: "새 과제안 고르기 (신규 영역)" })).toBeInTheDocument();
    const bar = screen.getByTestId("precheck-summary-bar");
    expect(within(bar).queryByRole("button", { name: "차별화 과제안 더 만들기" })).toBeNull();
    expect(within(bar).getByRole("button", { name: "선택 적용" })).toBeInTheDocument();

    const first = within(screen.getAllByTestId("novel-card")[0]!).getAllByTestId("novel-title")[0]!;
    await userEvent.click(within(first).getByRole("button", { name: "이 과제명으로 진행" }));
    expect(getIdea().request.title_hint).toBe("역 구내 드론 점검 승인·저비용 운용 체계 연구");
    expect(getIdea().request.idea_versions?.at(-1)).toMatchObject({ kind: "edited", fields: { title_hint: "역 구내 드론 점검 승인·저비용 운용 체계 연구" } });
    expect(within(first).getByRole("button", { name: "반영됨" })).toBeDisabled();
    expect((await screen.findAllByText("과제명을 가제 칸에 넣었습니다 — 고칠 수 있습니다.")).length).toBeGreaterThan(0);

    const input = screen.getByRole("textbox", { name: "과제명(가제)" });
    await userEvent.clear(input);
    await userEvent.type(input, "드론 점검 연구");
    expect(getIdea().request.title_hint).toBe("드론 점검 연구");
    expect(within(first).getByRole("button", { name: "이 과제명으로 진행" })).toBeEnabled();

    // novel 은 서버 카드 적용(/apply)을 부르지 않는다
    expect(calls.some((c) => c.url.includes("/apply"))).toBe(false);
    await waitFor(() => expect(calls.some((c) => c.url === "/v1/precheck/comparison")).toBe(true));
    expect(container.textContent).not.toMatch(INTERNAL_ID);
    expect(container.textContent).not.toMatch(/ip_blocked/);
    await expectNoA11yViolations(container);
  });

  it("differentiate + novelty_reverted — 차별화 제목·한 줄·더 만들기 보임", async () => {
    mockFetch({ "/v1/precheck/comparison": COMPARISON });
    startWith(diff({ mode: "differentiate", novelty_reverted: true, novelty_alert_ids: ["own:1"] }));
    renderWithProviders(<Precheck />, { route: "/new/precheck" });
    expect(screen.getByRole("heading", { level: 2, name: "차별화 과제안 고르기" })).toBeInTheDocument();
    expect(screen.getByTestId("novelty-reverted-note")).toHaveTextContent(NOVELTY_REVERTED_NOTE);
    expect(screen.getByRole("button", { name: "차별화 과제안 더 만들기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "이 안으로 진행" })).toBeInTheDocument();
    expect(screen.queryByTestId("novelty-coverage")).toBeNull();
  });
});

describe("카드 방식만 0건일 때 안내 (계약 problem-card.md 4.4절)", () => {
  const HINT = "문제 정의 카드 기준으로는 찾지 못했지만, 카드 없이 찾으면 3건이 있습니다. 핵심 문제 카드(기능 문장·대상)를 확인해 주세요.";
  const emptyReport = (over: Partial<AnalogyReport> = {}): AnalogyReport => ({
    kind: "other_field",
    heading: "다른 분야 사례",
    description: "철도 밖에서 비슷한 문제를 다룬 자료입니다(가짜 설명).",
    count: 0,
    dropped_weak: 0,
    sources_total: 4,
    sources_checked: 4,
    checked_labels: ["ScienceON", "OpenAlex", "KIPRIS", "NTIS"],
    unavailable: [],
    partial: false,
    languages: ["한국어", "영어"],
    scope_text: "자료원 4곳 중 4곳 확인",
    empty_text: "찾지 못했습니다(검색 범위: 한국어·영어, 자료원 4곳)",
    ...over,
  });

  it("card_hint 가 오면 0건 구획에 그 문장과 ① 로 가는 [카드 확인하러 가기] 링크 (axe 0)", async () => {
    const { container } = renderCards(novel({ analogies: [], analogy_report: emptyReport({ card_hint: HINT }) }));
    expect(screen.getByTestId("analogy-empty")).toBeInTheDocument();
    expect(screen.getByTestId("analogy-card-hint")).toHaveTextContent(HINT);
    const link = screen.getByRole("link", { name: "카드 확인하러 가기" });
    expect(link).toHaveAttribute("href", "/new");
    expect(screen.getByTestId("novel-analogies").textContent).not.toMatch(/legacy|card_hint/);
    await expectNoA11yViolations(container);
  });

  it("card_hint 가 없거나 null 이면 종전 0건 화면 그대로, 자료가 있으면 안내를 보이지 않는다", () => {
    for (const hint of [undefined, null]) {
      const view = renderCards(novel({ analogies: [], analogy_report: emptyReport({ card_hint: hint }) }));
      expect(screen.getByTestId("analogy-empty")).toBeInTheDocument();
      expect(screen.queryByTestId("analogy-card-hint")).toBeNull();
      expect(screen.queryByRole("link", { name: "카드 확인하러 가기" })).toBeNull();
      view.unmount();
    }
    renderCards(novel({ analogy_report: emptyReport({ count: 2, card_hint: HINT }) }));
    expect(screen.queryByTestId("analogy-card-hint")).toBeNull();
  });
});
