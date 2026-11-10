import { expect, test } from "@playwright/test";
import { expectNoRunWord, fillIdea, goPrecheck, login } from "./helpers";
import { expectNoInternalIds } from "./helpers-text";

// ② 새 과제안 갈래의 비슷한 자료 묶음 + 비교 분석 (계약 problem-card.md 4.6절).
// 가짜 서버의 과제안 응답(novel)에 묶음이 든 유추 목록을 끼워 넣고, 비교 분석 응답은 붙잡아 두었다가 푼다 —
// 목록이 먼저 보이고 표는 뒤에 채워지는지 본다. route.fetch 를 쓰므로 afterEach 에서 가로채기를 푼다.

const NEEDS_SOURCE = "초록으로는 구분 안 됨 — 원문 확인 필요";
const member = (n: number, title: string, year: number) => ({
  doc_id: `kipris_kr:10200000${n}`,
  title,
  source: "kipris_kr",
  source_label: "KIPRIS 특허",
  url: `https://example.org/patent/${n}`,
  year,
});
const ANALOGIES = [
  {
    ...member(1, "악취 역류 차단 장치 (가짜)", 2019),
    domain_label: "위생 설비",
    why_relevant: "악취 역류라는 같은 문제를 다룸",
    live: false,
    similarity: 0.9,
    similar: [member(2, "하수구 악취 역류 방지기 (가짜)", 2000), member(3, "악취 역류 방지장치 (가짜)", 2009)],
    group_id: "a1b2c3d4e5f6",
  },
  {
    doc_id: "scienceon:X1",
    title: "공중화장실 복합악취 저감 (가짜)",
    source: "scienceon",
    source_label: "ScienceON",
    domain_label: "환경",
    why_relevant: "악취 저감",
    url: null,
    year: 2021,
    live: false,
    similar: [],
    group_id: null,
  },
];
const row = (n: number, title: string, year: number, over: Record<string, unknown> = {}) => ({
  ...member(n, title, year),
  core_method: "배수 유닛 안에 수막을 만든다",
  difference: "싱크 배수용",
  use: "화장실 배수구에 수막 방식 검토",
  use_basis: "추정",
  limit: "물이 마르면 효과 없음",
  needs_source: false,
  ...over,
});
const ANALYSIS = {
  status: "ok",
  group_id: "a1b2c3d4e5f6",
  items: [
    row(1, "악취 역류 차단 장치 (가짜)", 2019),
    row(2, "하수구 악취 역류 방지기 (가짜)", 2000, { core_method: "판 높이차로 물막이", difference: "바닥 하수구용", limit: NEEDS_SOURCE, needs_source: true }),
    row(3, "악취 역류 방지장치 (가짜)", 2009, { core_method: "맨홀 덮개 개폐판", difference: "맨홀용" }),
  ],
  summary: { common: "물이나 판으로 배관을 막아 역류를 차단", gap: "환기와 함께 쓰는 방식" },
  cached: false,
  seconds: 1.2,
  reason_label: null,
};

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: "ignoreErrors" });
});

test("비슷한 자료 묶음 — 펼쳐 보기, 비교 표는 뒤에서 채워진다", async ({ page }) => {
  // 과제안 응답이 새 과제안 갈래면 유추 목록을 묶음이 든 것으로 바꾼다
  await page.route(/\/v1\/precheck\/recommendations(\?.*)?$/, async (route) => {
    const res = await route.fetch();
    const body = (await res.json()) as { recommendations?: { mode?: string; analogies?: unknown } };
    if (body.recommendations?.mode === "novel") body.recommendations.analogies = ANALOGIES;
    await route.fulfill({ response: res, json: body });
  });
  let release: () => void = () => undefined;
  const gate = new Promise<void>((r) => (release = r));
  const analyzeBodies: { request?: Record<string, unknown>; doc_ids?: string[] }[] = [];
  await page.route("**/v1/precheck/analogy-groups/analyze", async (route) => {
    analyzeBodies.push(route.request().postDataJSON() as (typeof analyzeBodies)[number]);
    await gate;
    await route.fulfill({ json: ANALYSIS });
  });

  await login(page);
  await fillIdea(page);
  await goPrecheck(page);

  // 첫 행을 [관련 없음] 으로 → 유사함 0건 → 새 과제안 갈래 (novel-recommend.spec 과 같은 길)
  const rows = page.getByRole("table", { name: /유사과제 목록/ }).locator("tbody tr");
  await expect(page.getByText(/'같다'·'일부 겹침' 으로 본 1건은 \[유사함\] 으로 미리 골랐습니다/)).toBeVisible();
  await expect(page.getByTestId("plan-card").first()).toBeVisible();
  await expect(rows.first().getByRole("button", { name: "유사함" })).toHaveAttribute("aria-pressed", "true");
  await rows.first().getByRole("button", { name: "관련 없음" }).click();
  await expect(rows.first().getByRole("button", { name: "관련 없음" })).toHaveAttribute("aria-pressed", "true");
  const bar = page.getByTestId("precheck-summary-bar");
  await expect(bar.getByText(/유사함 0건/)).toBeVisible();
  await bar.getByRole("button", { name: "선택 적용" }).click();
  await expect(page.locator("#plan-cards")).toHaveAttribute("data-mode", "novel");

  // 목록 먼저 — 묶음은 한 자리, 분석은 아직 기다리는 중
  const items = page.getByTestId("novel-analogy");
  await expect(items).toHaveCount(2);
  const group = items.first();
  await expect(group.getByTestId("analogy-group-waiting")).toHaveText("비교 분석 중…");
  await expect(page.getByTestId("analogy-group-table")).toHaveCount(0);
  await expect(items.nth(1).getByTestId("analogy-similar-toggle")).toHaveCount(0);

  // 펼치기 — 기다리는 동안에도 쓸 수 있다
  const toggle = group.getByTestId("analogy-similar-toggle");
  await expect(toggle).toHaveText("비슷한 자료 2건 더 보기");
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(group.getByTestId("analogy-similar-list")).toBeHidden();
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  const list = group.getByTestId("analogy-similar-list");
  await expect(list.getByRole("link", { name: /하수구 악취 역류 방지기/ })).toHaveAttribute("href", "https://example.org/patent/2");
  await expect(list).toContainText("KIPRIS 특허 · 2009");

  // 분석 요청 — 묶음 하나, 대표 + 비슷한 자료, 과제 입력이 함께 간다
  await expect.poll(() => analyzeBodies.length).toBe(1);
  expect(analyzeBodies[0]?.doc_ids).toEqual(["kipris_kr:102000001", "kipris_kr:102000002", "kipris_kr:102000003"]);
  expect(String(analyzeBodies[0]?.request?.goal ?? "")).toContain("보수 우선순위");

  // 응답이 오면 표와 요약이 채워진다
  release();
  const table = group.getByTestId("analogy-group-table");
  await expect(table).toBeVisible();
  await expect(group.getByTestId("analogy-group-waiting")).toHaveCount(0);
  await expect(table.getByRole("columnheader")).toHaveText(["자료", "핵심 방식", "다른 점", "이 과제에 활용할 점", "한계"]);
  await expect(table.getByTestId("analogy-group-row")).toHaveCount(3);
  await expect(table.getByTestId("analogy-group-basis")).toHaveText(["추정", "추정", "추정"]);
  await expect(table.getByTestId("analogy-group-source-link")).toHaveCount(1);
  await expect(table.getByTestId("analogy-group-source-link")).toHaveAttribute("href", "https://example.org/patent/2");
  const summary = group.getByTestId("analogy-group-summary");
  await expect(summary).toContainText("공통 접근 — 물이나 판으로 배관을 막아 역류를 차단");
  await expect(summary).toContainText("아직 다뤄지지 않은 부분 — 환기와 함께 쓰는 방식");
  expect(analyzeBodies).toHaveLength(1);

  await expectNoInternalIds(page);
  await expectNoRunWord(page);
});
