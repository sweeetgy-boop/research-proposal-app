import { expect, test } from "@playwright/test";
import { GUEST, STAFF_NO, createRun, loginGuest, loginStaff } from "./helpers";

const FAILED = "사번 또는 아이디·비밀번호를 확인하세요";

test.describe("로그인 (레인 A)", () => {
  test("직원 사번: 미등록은 통일 문구, 등록 사번은 통과·상단에 '직원'만 표시·로그아웃", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("tab", { name: "철도연구원 직원(사번)" })).toHaveAttribute("aria-selected", "true");
    await page.getByLabel("사번", { exact: true }).fill("NOPE-0000");
    await page.getByRole("button", { name: "로그인" }).click();
    await expect(page.getByRole("alert").filter({ hasText: FAILED })).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);

    await loginStaff(page);
    const badge = page.getByLabel("로그인 종류: 직원");
    await expect(badge).toBeVisible();
    await expect(page.locator("header")).not.toContainText(STAFF_NO); // 사번 표시 금지
    expect(await page.evaluate(() => JSON.stringify(sessionStorage))).not.toContain(STAFF_NO);
    await page.getByRole("button", { name: "로그아웃" }).click();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("공용 계정: 틀린 비밀번호는 통일 문구, 맞으면 통과·'공용 계정' 표시·run 은 자기 것만", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("tab", { name: "그 외 사용자(아이디·비밀번호)" }).click();
    await page.getByLabel("아이디", { exact: true }).fill(GUEST.id);
    await page.getByLabel("비밀번호", { exact: true }).fill("wrong-password");
    await page.getByRole("button", { name: "로그인" }).click();
    await expect(page.getByRole("alert").filter({ hasText: FAILED })).toBeVisible();

    await loginGuest(page);
    await expect(page.getByLabel("로그인 종류: 공용 계정")).toBeVisible();
    const id = await createRun(page);
    await page.getByRole("link", { name: "run 목록" }).click();
    await expect(page.getByText(id)).toBeVisible();
    await page.getByRole("button", { name: "로그아웃" }).click();

    // 다른 직원으로 들어오면 공용 계정의 run 은 보이지 않고 직접 열어도 404
    await loginStaff(page, "E2E-0002");
    await page.getByRole("link", { name: "run 목록" }).click();
    await expect(page.getByText(id)).toHaveCount(0);
    await page.goto(`/runs/${id}`);
    await expect(page.getByText(/run 을 찾을 수 없습니다|없음/).first()).toBeVisible();
  });
});
