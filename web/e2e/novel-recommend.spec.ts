import { expect, test } from "@playwright/test";
import { fillIdea, login, goPrecheck } from "./helpers";
import { expectNoInternalIds } from "./helpers-text";

// ② 과제안 두 갈래 (ADR 0057, 가짜 모드). 기본 아이디어는 첫 행이 '일부 겹침' → [유사함] 1건 → 차별화 과제안.
// 그 행을 [관련 없음] 으로 바꿔 [선택 적용] 하면 유사함 0·차단 없음 → 새 과제안(신규 영역) 갈래.

test("유사함 1건 이상 → 기존 '차별화 과제안 고르기' 그대로", async ({ page }) => {
  await login(page);
  await fillIdea(page);
  await goPrecheck(page);

  const bar = page.getByTestId("precheck-summary-bar");
  await expect(bar.getByText(/유사함 1건/)).toBeVisible();
  await expect(page.locator("#plan-cards-heading")).toHaveText("차별화 과제안 고르기");
  await expect(page.locator("#plan-cards")).toHaveAttribute("data-mode", "differentiate");
  await expect(page.getByTestId("plan-card").first()).toBeVisible();
  await expect(page.getByTestId("novel-card")).toHaveCount(0);
  await expect(page.getByTestId("novelty-coverage")).toHaveCount(0);
  await expect(bar.getByRole("button", { name: /차별화 과제안 더 만들기/ })).toBeVisible();
});

test("유사함 0건 → '새 과제안' 제목·확인 범위·장벽 배지·과제명 선택 → 가제 반영", async ({ page }) => {
  await login(page);
  await fillIdea(page);
  await goPrecheck(page);

  const table = page.getByRole("table", { name: /유사과제 목록/ });
  const rows = table.locator("tbody tr");
  await expect(rows.first().getByRole("button", { name: "유사함" })).toHaveAttribute("aria-pressed", "true");
  await rows.first().getByRole("button", { name: "관련 없음" }).click();
  const bar = page.getByTestId("precheck-summary-bar");
  await expect(bar.getByText(/유사함 0건/)).toBeVisible();
  await bar.getByRole("button", { name: "선택 적용" }).click();

  // 갈래 제목과 확인 범위 — 가짜 모드는 실시간 검색이 꺼져 있어 저장 자료 범위
  await expect(page.locator("#plan-cards-heading")).toHaveText("새 과제안 고르기 (신규 영역)");
  await expect(page.locator("#plan-cards")).toHaveAttribute("data-mode", "novel");
  const coverage = page.getByTestId("novelty-coverage");
  await expect(coverage).toContainText("저장 자료 범위 안에서 기존 과제가 없습니다");
  await expect(coverage).toContainText("확인한 자료원:");
  await expect(page.getByTestId("novel-unavailable")).toContainText("확인 못 함");

  // 안 카드 2건 — 성숙도·장벽 유형·근거 수준 배지
  const cards = page.getByTestId("novel-card");
  await expect(cards).toHaveCount(2);
  const first = cards.first();
  await expect(first.getByTestId("novel-maturity")).toBeVisible();
  await expect(first.getByTestId("barrier-type").first()).toHaveText(/^(수요|규제|비용|기술|운영)$/);
  await expect(page.getByTestId("barrier-basis").filter({ hasText: "근거 있음" }).first()).toBeVisible();
  await expect(page.getByTestId("barrier-basis").filter({ hasText: "추정" }).first()).toBeVisible();
  await expect(page.getByText(/확인 방법:/).first()).toBeVisible();

  // 장벽 해소형 과제명 — "해소: …" 배지 + [이 과제명으로 진행] → 가제 칸에 들어가고 고칠 수 있다
  const title = first.getByTestId("novel-title").first();
  await expect(title.getByTestId("title-resolves")).toHaveText(/^해소: /);
  const hint = page.getByTestId("novel-title-hint");
  await title.getByRole("button", { name: "이 과제명으로 진행" }).click();
  // 가제 칸 값이 그 과제명과 같을 때만 버튼이 "반영됨" 으로 꺼진다
  await expect(title.getByRole("button", { name: "반영됨" })).toBeDisabled();
  const name = await hint.inputValue();
  expect(name.length).toBeGreaterThan(0);
  await expect(title).toContainText(name);
  await hint.fill(`${name} (수정)`);
  await expect(hint).toHaveValue(`${name} (수정)`);
  await expect(title.getByRole("button", { name: "이 과제명으로 진행" })).toBeEnabled();

  // 새 과제안은 [더 만들기] 가 없다
  await expect(bar.getByRole("button", { name: /차별화 과제안 더 만들기/ })).toHaveCount(0);
  await expectNoInternalIds(page);
});
