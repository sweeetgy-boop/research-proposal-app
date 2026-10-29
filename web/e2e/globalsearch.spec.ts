/** [UI] 위쪽 통합 검색 (2026-10-29 레인 3) — 제안서·자료 두 묶음, 키보드(Ctrl+K·↑↓·Enter·Esc),
 *  자료 → 근거 패널, [자료 전체 결과 보기] → 자료 검색(자료원·연도 거르기), 공용 계정 internal 제외. */
import { expect, test, type Page } from "@playwright/test";
import { createRun, login, loginGuest } from "./helpers";
import { expectNoInternalIds } from "./helpers-text";

const combobox = (page: Page) => page.getByRole("combobox", { name: "제안서·자료 통합 검색" });
const listbox = (page: Page) => page.getByRole("listbox", { name: "통합 검색 결과" });

test("입력 → 두 묶음 → ↓·Enter 로 제안서가 열린다, Esc 닫기", async ({ page }) => {
  await login(page);
  const id = await createRun(page);
  const runs = await page.request.get("/v1/runs?limit=50");
  const run = ((await runs.json()) as { runs: { run_id: string; title: string | null }[] }).runs.find((r) => r.run_id === id)!;
  const word = (run.title ?? "").trim().split(/\s+/)[0]!;
  expect(word.length).toBeGreaterThan(0);

  await page.goto("/runs");
  await expect(page.getByRole("heading", { name: "내 제안서" })).toBeVisible();
  await page.keyboard.press("Control+k");
  await expect(combobox(page)).toBeFocused();
  await page.keyboard.type(word);
  const proposals = listbox(page).getByRole("group", { name: "내 제안서" });
  const docs = listbox(page).getByRole("group", { name: "자료" });
  await expect(proposals.getByRole("option").first()).toBeVisible();
  await expect(docs.getByRole("option").first()).toBeVisible();
  await expect(listbox(page).getByRole("option", { name: "자료 전체 결과 보기" })).toBeVisible();
  await expectNoInternalIds(page);

  await page.keyboard.press("Escape");
  await expect(listbox(page)).toBeHidden();
  await expect(combobox(page)).toBeFocused();

  await page.keyboard.press("ArrowDown"); // 다시 연다
  await expect(listbox(page)).toBeVisible();
  await page.keyboard.press("ArrowDown");
  await expect(proposals.getByRole("option").first()).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(new RegExp(`/runs/${id}(/[a-z-]+)?$`));
});

test("자료 결과 → 근거 패널(요약·원문), [자료 전체 결과 보기] → 자료원·연도 거르기", async ({ page }) => {
  await login(page);
  await combobox(page).fill("궤도");
  const docs = listbox(page).getByRole("group", { name: "자료" });
  const first = docs.getByRole("option").first();
  await expect(first).toBeVisible();
  const title = (await first.locator("span.font-medium").first().innerText()).trim();
  await first.click();
  const dialog = page.getByRole("dialog", { name: title });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(/원문|요약이 없습니다/).first()).toBeVisible();
  await dialog.getByRole("button", { name: "닫기" }).click();
  await expect(combobox(page)).toBeFocused();

  await combobox(page).fill("궤도");
  await listbox(page).getByRole("option", { name: "자료 전체 결과 보기" }).click();
  await expect(page).toHaveURL(/\/search\?q=%EA%B6%A4%EB%8F%84$/);
  await expect(page.getByRole("heading", { name: "자료 검색" })).toBeVisible();
  const results = page.getByTestId("search-results");
  await expect(results.getByRole("listitem").first()).toBeVisible();
  await expectNoInternalIds(page);

  // 연도 거르기 — 2025 년 자료(가짜 연구용역)만
  await page.getByLabel("시작").fill("2025");
  await page.getByLabel("끝").fill("2025");
  await page.getByRole("button", { name: "연도 적용" }).click();
  await expect(page).toHaveURL(/year_from=2025&year_to=2025/);
  await expect(results.getByRole("listitem").first()).toBeVisible();
  await expect(results.getByRole("listitem").filter({ hasNotText: "2025년" })).toHaveCount(0);

  // 자료원 거르기
  await page.getByRole("button", { name: "조건 지우기" }).click();
  const openalex = page.getByRole("checkbox", { name: /OpenAlex/ });
  await openalex.click();
  await expect(openalex).toBeChecked();
  await expect(page).toHaveURL(/sources=openalex/);
  await expect(results.getByRole("listitem").first()).toBeVisible();
  await expect(results.getByRole("listitem").filter({ hasNotText: "OpenAlex" })).toHaveCount(0);
});

test("공용 계정은 통합 검색에서 사내 전용 자료가 보이지 않는다", async ({ page }) => {
  await loginGuest(page);
  await combobox(page).fill("궤도");
  const docs = listbox(page).getByRole("group", { name: "자료" });
  await expect(docs.getByRole("option").first()).toBeVisible();
  await expect(listbox(page).getByText("궤도 상태 자동 감지 연구 (가짜)")).toHaveCount(0);
  const r = await page.request.get("/v1/search/docs?q=%EA%B6%A4%EB%8F%84&limit=30");
  expect(await r.text()).not.toContain("궤도 상태 자동 감지 연구");
});

test("로그인 전에는 결과를 열지 않고 API 도 데이터를 주지 않는다", async ({ page }) => {
  await page.goto("/login");
  await page.keyboard.press("Control+k");
  await expect(page).toHaveURL(/\/login$/);
  await expect(listbox(page)).toBeHidden();
  const r = await page.request.get("/v1/search/docs?q=%EA%B6%A4%EB%8F%84");
  expect(r.status()).toBe(401);
});
