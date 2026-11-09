import { expect, test, type Page } from "@playwright/test";
import { fillIdea, login, goPrecheck } from "./helpers";
import { expectNoInternalIds } from "./helpers-text";

// ② 과제안 갈래 전환 — novel ↔ 차별화 (2026-11-09 레인 B, ADR 0061, 가짜 모드).
// 선택을 바꿔 [선택 적용] 한 번이면 새 갈래의 과제안 카드가 보인다(409 없음). 기본 아이디어는 첫 행이
// '일부 겹침' → [유사함] 1건 → 차별화; "(중복)" 이 있으면 첫 행이 '같다' → 차단.

const summaryBar = (page: Page) => page.getByTestId("precheck-summary-bar");
const firstRow = (page: Page) => page.getByRole("table", { name: /유사과제 목록/ }).locator("tbody tr").first();

async function waitDifferentiateCards(page: Page) {
  await expect(page.locator("#plan-cards-heading")).toHaveText("차별화 과제안 고르기");
  await expect(page.locator("#plan-cards")).toHaveAttribute("data-mode", "differentiate");
  await expect(page.getByTestId("plan-card").first()).toBeVisible();
  await expect(page.getByTestId("novel-card")).toHaveCount(0);
}

async function waitNovelCards(page: Page) {
  await expect(page.locator("#plan-cards-heading")).toHaveText("새 과제안 고르기 (신규 영역)");
  await expect(page.locator("#plan-cards")).toHaveAttribute("data-mode", "novel");
  await expect(page.getByTestId("novel-card").first()).toBeVisible();
  await expect(page.getByTestId("plan-card")).toHaveCount(0);
}

test("(a) 새 과제안(novel) 화면에서 행을 [유사함] 으로 되돌려 [선택 적용] → 차별화 과제안 카드", async ({ page }) => {
  await login(page);
  await fillIdea(page);
  await goPrecheck(page);

  // AI 판정의 기본 선택([유사함] 1건)과 첫 차별화 과제안이 뜬 뒤에 선택을 바꾼다
  await expect(page.getByText(/'같다'·'일부 겹침' 으로 본 1건은 \[유사함\] 으로 미리 골랐습니다/)).toBeVisible();
  await waitDifferentiateCards(page);
  const row = firstRow(page);
  await row.getByRole("button", { name: "관련 없음" }).click();
  await summaryBar(page).getByRole("button", { name: "선택 적용" }).click();
  await waitNovelCards(page);
  await expect(summaryBar(page).getByRole("button", { name: /차별화 과제안 더 만들기/ })).toHaveCount(0);

  // (a) 되돌리기: 같은 행을 다시 [유사함] 으로 → [선택 적용] 한 번 → 차별화 카드로 돌아온다 (409 없음)
  await row.getByRole("button", { name: "유사함" }).click();
  await expect(summaryBar(page).getByText(/유사함 1건/)).toBeVisible();
  await summaryBar(page).getByRole("button", { name: "선택 적용" }).click();
  await waitDifferentiateCards(page);
  await expect(page.getByTestId("novelty-coverage")).toHaveCount(0);
  await expect(summaryBar(page).getByRole("button", { name: /차별화 과제안 더 만들기/ })).toBeVisible();
  // 차별화 카드는 그대로 고를 수 있다(세션이 새 갈래로 바뀌었으니 409 가 아니다)
  await page.getByTestId("plan-card").first().getByRole("button", { name: "이 안으로 진행" }).click();
  await expect(page.getByTestId("plan-card").first().getByRole("button", { name: "이 안으로 진행 중" })).toBeVisible();
  await expect(page.locator("body")).not.toContainText("새 과제안은");
  await expectNoInternalIds(page);
});

test("(b) 차단 행이 있는 차별화 화면에서 모두 [관련 없음] → 차단 해제 → [선택 적용] → 새 과제안(novel) 카드", async ({ page }) => {
  await login(page);
  await fillIdea(page, " (중복)");
  await goPrecheck(page);

  // '같다'(차단) 행 — 기본 선택은 [유사함], 차단 경보와 차별화 과제안
  await expect(page.getByRole("alert").filter({ hasText: "차단 경보" })).toBeVisible();
  await expect(page.getByText(/'같다'·'일부 겹침' 으로 본 1건은 \[유사함\] 으로 미리 골랐습니다/)).toBeVisible();
  await waitDifferentiateCards(page);

  // 차단 행을 [관련 없음] 으로 — 차단이 풀리고 유사함 0건
  await firstRow(page).getByRole("button", { name: "관련 없음" }).click();
  await expect(page.getByText("차단 과제를 모두 [관련 없음] 으로 골라 차단 경보를 풀었습니다.")).toBeVisible();
  await expect(summaryBar(page).getByText(/유사함 0건/)).toBeVisible();
  await summaryBar(page).getByRole("button", { name: "선택 적용" }).click();

  // 유사함 0·차단 없음 → novel 갈래의 카드가 한 번에 보인다
  await waitNovelCards(page);
  await expect(page.getByTestId("novelty-coverage")).toContainText("저장 자료 범위 안에서 기존 과제가 없습니다");
  await expect(summaryBar(page).getByRole("button", { name: /차별화 과제안 더 만들기/ })).toHaveCount(0);
  await expect(page.locator("body")).not.toContainText("새 과제안은");
  await expectNoInternalIds(page);
});
