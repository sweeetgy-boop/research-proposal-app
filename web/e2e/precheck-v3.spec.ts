import { expect, test } from "@playwright/test";
import { fillIdea, login } from "./helpers";

// ② v3 (레인 A, ADR 0039, 가짜 모드): 표 먼저 → AI 판정 → [유사함] → [선택 적용] → 비교표 갱신 → [차별화 과제안 더 만들기]
const INTERNAL = /\b(own|alio|ntis|scienceon|openalex|korail_web|g2b):[\w-]+/;

test("② 표 먼저·선택 적용·과제안 더 만들기 — 내부 번호 없음", async ({ page }) => {
  await login(page);
  await fillIdea(page);
  await page.getByRole("button", { name: "유사과제 확인" }).click();
  await expect(page).toHaveURL(/\/new\/precheck$/);

  const table = page.getByRole("table", { name: /유사과제 목록/ });
  await expect(table).toBeVisible();
  // AI 판정이 오면 판정 칸이 AI 기준(가짜: 첫 행 일부 겹침 → 근접, 나머지 다르다 → 관련 낮음)
  await expect(table.getByText("관련 낮음").first()).toBeVisible();
  await expect(page.getByText(/'다르다' 로 본 \d+건은 \[관련 없음\]/)).toBeVisible();

  const bar = page.getByTestId("precheck-summary-bar");
  await expect(bar).toBeVisible();
  const rows = table.locator("tbody tr");
  await rows.first().getByRole("button", { name: "유사함" }).click();
  await expect(bar.getByText(/유사함 1건/)).toBeVisible();
  await expect(bar.getByText(/선택이 바뀌었습니다/)).toBeVisible();
  await bar.getByRole("button", { name: "선택 적용" }).click();
  await expect(bar.getByText("선택 적용됨 · 비교표 갱신")).toBeVisible();
  const compare = page.getByRole("table", { name: /차별성 비교표/ });
  await expect(compare).toBeVisible();

  // 과제안 카드 → [차별화 과제안 더 만들기] → 새 카드
  const cards = page.getByTestId("plan-card");
  await expect(cards.first()).toBeVisible();
  const before = await cards.count();
  await bar.getByRole("button", { name: "차별화 과제안 더 만들기" }).click();
  await expect(cards).toHaveCount(before + 2);
  await expect(page.getByText("새로 만든 안").first()).toBeVisible();

  // ② 화면 어디에도 내부 문서 번호·유사도 숫자가 없다
  const text = await page.locator("body").innerText();
  expect(text).not.toMatch(INTERNAL);
  expect(text).not.toMatch(/유사도 0\.\d+/);

  const dir = process.env.RRA_SCREENS_DIR;
  if (dir) await page.screenshot({ path: `${dir}/2026-10-28-precheck-v3-flow.png`, fullPage: true });
});
