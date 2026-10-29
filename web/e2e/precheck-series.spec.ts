import { expect, test } from "@playwright/test";
import { detailMode, expectNoRunWord, login, goPrecheck } from "./helpers";
import { expectNoInternalIds } from "./helpers-text";

// ② 같은 연작 한 줄 (레인 A, ADR 0043, 가짜 모드): 제목이 연도만 다른 사내 과제 3판이 "○○(연작 3건)" 한 줄 →
// [펼치기] 연도별 목록 → 판을 누르면 근거 패널 → 행 [유사함] 은 묶음 전체. 다른 과제는 따로 한 줄.
test("② 같은 연작 한 줄 — 펼치기·근거 패널·묶음 선택, 내부 번호 없음", async ({ page }) => {
  await login(page);
  await detailMode(page);
  await page.getByLabel(/현재 상황·문제/).fill("광역철도 수송수요예측 오차가 신설역 개통 때 커짐");
  await page.getByLabel(/발생 원인/).fill("연도별 수송수요예측 모형이 신설역 효과를 반영하지 못함");
  await page.getByLabel(/현행 대응의 한계/).fill("광역철도 월별 변동을 다루지 않음");
  await page.getByLabel(/해결 목표/).fill("광역철도 수송수요예측 모형 개선");
  await goPrecheck(page);
  await expect(page).toHaveURL(/\/new\/precheck$/);

  const table = page.getByRole("table", { name: /유사과제 목록/ });
  await expect(table).toBeVisible();
  const row = table.locator('tbody tr[data-series="true"]');
  await expect(row).toHaveCount(1);
  await expect(row.getByText(/\(연작 3건\)$/)).toBeVisible();
  await expect(row.getByText("사내 과제 · 알리오 공시")).toBeVisible();
  await expect(table.getByText("광역철도 신설역 개통 효과 분석 (가짜)")).toBeVisible(); // 다른 과제는 따로

  await row.getByRole("button", { name: "펼치기" }).click();
  const list = row.getByRole("list", { name: /연도별 목록/ });
  await expect(list.getByRole("listitem")).toHaveCount(3);
  await expect(list.getByRole("listitem").first()).toContainText("2023");
  await expect(list.getByRole("listitem").nth(1)).toContainText(/사내 과제 · 알리오 공시|알리오 공시 · 사내 과제/);

  // 판 하나 → 근거 패널(요약·원문 안내)
  await list.getByRole("button", { name: /2024년도 .* 근거 보기/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(/연작 표본/)).toBeVisible();
  await expectNoInternalIds(page, dialog);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();

  // 행 [유사함] 은 묶음 하나 — 선택 요약 막대 "유사함 1건"
  await row.getByRole("button", { name: "유사함" }).click();
  await expect(page.getByTestId("precheck-summary-bar").getByText(/유사함 1건/)).toBeVisible();
  await expect(row.getByRole("button", { name: "유사함" })).toHaveAttribute("aria-pressed", "true");
  await expect(row.getByRole("button", { name: "관련 없음" })).toHaveAttribute("aria-pressed", "false");

  await expectNoInternalIds(page);
  await expectNoRunWord(page);
  const dir = process.env.RRA_SCREENS_DIR;
  if (dir) {
    await page.mouse.move(0, 0);
    await page.waitForTimeout(400); // 버튼 색 전환이 끝난 뒤
  }
  if (dir) await page.screenshot({ path: `${dir}/2026-10-29-precheck-series-row.png`, fullPage: true });
  await row.getByRole("button", { name: "접기" }).click();
  await expect(row.getByRole("list", { name: /연도별 목록/ })).toHaveCount(0);
});
