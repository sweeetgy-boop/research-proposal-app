/** ADR 0045 — 초안 글 먼저, 그림은 백그라운드. 가짜 백엔드는 그림마다 RRA_FAKE_FIGURE_DELAY 초(기본 3) 기다린다.
 *  초안 본문이 먼저 보이고 → "그림 준비 중" 카드·한 줄 → 그림이 그 자리에 들어온다. 그리는 동안 최종 검토는 기다린다. */
import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { createRun, login, subnav, expectNoRunWord } from "./helpers";
import { expectNoInternalIds } from "./helpers-text";

const SHOTS = process.env.RRA_SHOTS; // 화면 기록: docs/history/screens

async function shot(page: Page, name: string) {
  if (!SHOTS) return;
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `2026-10-29-draft-first-${name}.png`), fullPage: false });
}

test.describe("초안 글 먼저 · 그림은 백그라운드", () => {
  test("초안 본문 → 그림 준비 중 → 그림 도착, 그리는 동안 최종 검토는 기다린다", async ({ page }) => {
    await login(page);
    const id = await createRun(page);

    // 초안 글은 이미 보인다 (문장이 있다)
    await expect(page.getByRole("heading", { name: "초안 본문" })).toBeVisible();
    await expect(page.getByText(/근거 \d+건 보기/).first()).toBeVisible();
    // 그림은 아직 준비 중 — 한 줄 안내와 자리 카드
    const job = page.getByTestId("figure-job");
    await expect(job.getByText("그림 준비 중", { exact: true }).first()).toBeVisible();
    await expect(page.getByTestId("figure-slot").first()).toBeVisible();
    await page.getByTestId("figure-slot").first().scrollIntoViewIfNeeded();
    await shot(page, "drawing");
    await expectNoInternalIds(page);
    await expectNoRunWord(page);

    // 그리는 동안 최종 검토 단계는 기다린다
    await subnav(page, "최종 검토").click();
    await expect(page).toHaveURL(new RegExp(`/runs/${id}/final-review$`));
    const hint = page.getByTestId("figures-pending-hint");
    const start = page.getByRole("button", { name: "최종 검토 요청" });
    if (await hint.isVisible()) await expect(start).toBeDisabled();

    // 그림이 다 오면 안내가 사라지고 요청할 수 있다
    await expect(hint).toBeHidden({ timeout: 20_000 });
    await expect(start).toBeEnabled();

    // 초안 보기: 그림 카드가 자리에 들어왔다 (자리 카드 없음)
    await subnav(page, "초안 보기").click();
    await expect(page.getByRole("group", { name: "현재·연구 후 비교 그림" })).toBeVisible();
    await expect(page.getByTestId("figure-slot")).toHaveCount(0);
    await expect(page.getByTestId("figure-job")).toHaveCount(0);
    await page.getByRole("group", { name: "현재·연구 후 비교 그림" }).scrollIntoViewIfNeeded();
    await shot(page, "ready");
    await expectNoInternalIds(page);
  });
});
