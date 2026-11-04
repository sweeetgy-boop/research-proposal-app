/** ADR 0055 — Argon 연결 오류 알림 띠. 가짜 백엔드는 함께 쓰는 서버라 RRA_FAKE_GEMINI_STATUS 를 켜면 다른 spec 에도
 *  띠가 보이므로, 이 spec 만 /healthz 응답을 가로채 llm.gemini 를 key_invalid 로 바꾼다(나머지 필드는 서버 그대로). */
import { expect, test, type Page } from "@playwright/test";
import { login, loginStaff } from "./helpers";
import { expectNoInternalIds } from "./helpers-text";

const TITLE = "AI(Argon) 연결 오류 — 로컬 모델로 대체 중";

async function argonDown(page: Page, gemini = "key_invalid") {
  await page.route("**/healthz", async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    await route.fulfill({ response: res, json: { ...body, llm: { gemini, since: "2026-11-03T16:14:49+09:00" } } });
  });
}

const banner = (page: Page) => page.getByTestId("argon-status-banner");

test("Argon 키 무효: 로그인 전 띠 없음 → 직원은 제목만, 관리자는 사유 줄까지", async ({ page }) => {
  await argonDown(page);
  await page.goto("/");
  await expect(page.getByRole("group", { name: "로그인 전" })).toBeVisible();
  await expect(banner(page)).toHaveCount(0);

  await loginStaff(page);
  await expect(banner(page)).toBeVisible();
  await expect(banner(page)).toHaveAttribute("role", "status");
  await expect(banner(page)).toContainText(TITLE);
  await expect(page.getByText("API 키 확인 필요")).toHaveCount(0);
  await expect(page.locator("body")).not.toContainText("key_invalid");
  await expectNoInternalIds(page);
  // 다른 화면으로 옮겨도 그대로 (화면 틀)
  await page.getByRole("navigation", { name: "주 메뉴", exact: true }).getByRole("link", { name: /내 제안서/ }).click();
  await expect(page.getByRole("heading", { name: "내 제안서" })).toBeVisible();
  await expect(banner(page)).toContainText(TITLE);

  await page.getByRole("button", { name: "로그아웃" }).click();
  await expect(banner(page)).toHaveCount(0);

  await login(page); // 관리자 토큰
  await expect(banner(page)).toContainText(TITLE);
  await expect(page.getByTestId("argon-status-reason")).toHaveText("API 키 확인 필요");
});
