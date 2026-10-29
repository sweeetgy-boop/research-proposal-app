/** [UI] 화면 틀 — 화면 안 로그인, 사이드바 이동, 경로 표시, 좁은 화면 접는 메뉴 (레인 1). */
import { expect, test, type Page } from "@playwright/test";
import { STAFF_NO, login, openLoginDialog } from "./helpers";
import { expectNoInternalIds } from "./helpers-text";

const sidebar = (page: Page) => page.getByRole("navigation", { name: "주 메뉴", exact: true });
const crumbs = (page: Page) => page.getByRole("navigation", { name: "현재 위치" });

test.describe("화면 틀 (레인 1)", () => {
  test("로그인 전 홈 → 홈의 로그인 카드로 로그인 → 사이드바에 로그인 종류·건수", async ({ page }) => {
    await page.goto("/");
    // 처음부터 사이드바 + 홈, 로그인 전에는 개인 데이터(건수) 없음
    await expect(sidebar(page).getByRole("link", { name: "연구 작업실" })).toBeVisible();
    await expect(page.getByRole("group", { name: "로그인 전" })).toBeVisible();
    await expect(page.getByLabel(/^\d+건$/)).toHaveCount(0);
    const main = page.getByRole("main");
    await main.getByRole("tab", { name: "철도연구원 직원(사번)" }).click();
    await main.getByLabel("사번", { exact: true }).fill(STAFF_NO);
    await main.getByRole("button", { name: "로그인", exact: true }).click();
    await expect(page.getByRole("group", { name: "로그인 종류: 직원" })).toBeVisible();
    // 화면 이동 없이 같은 자리 — 로그인 카드가 "연구 한눈에 보기"로 바뀌고 최근 제안서 표가 채워진다(레인 2 홈)
    await expect(page).toHaveURL(/\/$/);
    await expect(main.getByTestId("home-login")).toHaveCount(0);
    await expect(main.getByText("연구 한눈에 보기")).toBeVisible();
    await expect(main.getByTestId("overview-all")).toContainText(/\d+\s*편/);
    await expect(sidebar(page).getByRole("link", { name: /내 제안서/ }).getByLabel(/^\d+건$/)).toBeVisible();
    await expect(page.locator("body")).not.toContainText(STAFF_NO); // 사번 표시 금지
    // 로그아웃 → 같은 홈의 로그인 전 상태
    await page.getByRole("button", { name: "로그아웃" }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("group", { name: "로그인 전" })).toBeVisible();
    await expect(page.getByRole("dialog", { name: "로그인" })).toBeHidden();
  });

  test("로그인 전 [새 제안서] → 그 자리에 로그인 창 → 로그인하면 ① 입력", async ({ page }) => {
    await page.goto("/");
    await sidebar(page).getByRole("link", { name: "새 제안서" }).click();
    const dialog = page.getByRole("dialog", { name: "로그인" });
    await expect(dialog).toBeVisible();
    await expect(page).toHaveURL(/\/new$/);
    await dialog.getByLabel("사번", { exact: true }).fill(STAFF_NO);
    await dialog.getByRole("button", { name: "로그인", exact: true }).click();
    await expect(dialog).toBeHidden();
    await expect(page.getByRole("heading", { name: /아이디어 입력/ }).first()).toBeVisible();
    await expect(page).toHaveURL(/\/new$/);
  });

  test("로그인 전 내 제안서·제안서 주소·통합 검색 → 로그인 창, 로그인 뒤 그 화면", async ({ page }) => {
    let dialog = await openLoginDialog(page, "/runs");
    await dialog.getByLabel("사번", { exact: true }).fill(STAFF_NO);
    await dialog.getByRole("button", { name: "로그인", exact: true }).click();
    await expect(page.getByRole("heading", { name: "내 제안서" })).toBeVisible();
    await page.getByRole("button", { name: "로그아웃" }).click();
    await expect(page).toHaveURL(/\/$/);

    // 통합 검색 자리 — 로그인 전이면 창
    await page.getByRole("combobox", { name: "제안서·자료 통합 검색" }).click();
    dialog = page.getByRole("dialog", { name: "로그인" });
    await expect(dialog).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });

  test("사이드바 이동 — 메뉴마다 선택 표시와 경로 표시", async ({ page }) => {
    await login(page);
    const nav = sidebar(page);
    await expect(nav.getByRole("link", { name: "새 제안서" })).toHaveAttribute("aria-current", "page");
    await expect(crumbs(page)).toContainText("Research Studio");
    await expect(crumbs(page)).toContainText("① 아이디어 입력");

    await nav.getByRole("link", { name: /내 제안서/ }).click();
    await expect(page).toHaveURL(/\/runs$/);
    await expect(nav.getByRole("link", { name: /내 제안서/ })).toHaveAttribute("aria-current", "page");
    await expect(crumbs(page).locator('[aria-current="page"]')).toHaveText("내 제안서");

    await page.getByRole("link", { name: "자료 현황" }).click();
    await expect(page).toHaveURL(/\/sources$/);
    await expect(crumbs(page).locator('[aria-current="page"]')).toHaveText("자료 현황");

    await expect(page.getByRole("link", { name: "작성 가이드" }).first()).toHaveAttribute("href", "/guide");
    await expect(nav.getByRole("link", { name: "연구 작업실" })).toHaveAttribute("href", "/");
    await nav.getByRole("link", { name: "새 제안서" }).click();
    await expect(page).toHaveURL(/\/new$/);
    await expectNoInternalIds(page);
  });

  test("좁은 화면(390px) — 접는 메뉴: 열기·Esc 닫기·메뉴로 이동", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page);
    await expect(sidebar(page)).toBeHidden(); // 고정 사이드바는 숨김
    const open = page.getByRole("button", { name: "메뉴 열기" });
    await open.click();
    const menu = page.getByRole("dialog", { name: "메뉴" });
    await expect(menu).toBeVisible();
    await expect(open).toHaveAttribute("aria-expanded", "true");
    await page.keyboard.press("Escape");
    await expect(menu).toBeHidden();
    await expect(open).toHaveAttribute("aria-expanded", "false");

    await open.click();
    await menu.getByRole("link", { name: /내 제안서/ }).click();
    await expect(page).toHaveURL(/\/runs$/);
    await expect(menu).toBeHidden();
    await expect(page.getByRole("heading", { name: "내 제안서" })).toBeVisible();
    // 가로 넘침 없음
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
