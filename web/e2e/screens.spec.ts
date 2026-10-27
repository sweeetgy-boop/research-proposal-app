/** 화면 캡처 — docs/screens/ 와 docs/history/screens/ 에 쓴다 (e2e 와 같은 가짜 백엔드). */
import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fillIdea, login, subnav } from "./helpers";

const OUT = process.env.RRA_SCREENS_DIR ?? "";
test.skip(!OUT, "RRA_SCREENS_DIR 가 없으면 건너뜀");

async function shot(page: import("@playwright/test").Page, n: number, name: string) {
  fs.mkdirSync(OUT, { recursive: true });
  await page.screenshot({ path: path.join(OUT, `${String(n).padStart(2, "0")}-${name}.png`), fullPage: true });
}

test("모든 화면 캡처", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/login");
  await shot(page, 1, "login");
  await login(page);
  await fillIdea(page);
  await shot(page, 2, "idea");
  await page.getByRole("button", { name: "유사과제 확인" }).click();
  await expect(page).toHaveURL(/precheck/);
  await shot(page, 3, "precheck");
  await page.getByRole("button", { name: /다음: 보강 질문/ }).click();
  await expect(page.getByText("보강 질문 없음")).toBeVisible();
  await shot(page, 4, "clarify");
  await page.getByRole("button", { name: "초안 생성 시작" }).click();
  await expect(page.getByRole("heading", { name: "초안 본문" })).toBeVisible({ timeout: 30_000 });
  const id = /\/runs\/([0-9-]+)/.exec(page.url())![1]!;
  await subnav(page, "진행").click();
  await shot(page, 5, "progress");
  await subnav(page, "초안 보기").click();
  await shot(page, 6, "draft");
  await subnav(page, "직접 수정").click();
  const group = page.getByRole("radiogroup", { name: "2-나 연구목적 문장 1 처리" });
  await group.getByText("직접 수정", { exact: true }).click();
  await shot(page, 7, "edit");
  await page.getByRole("textbox", { name: /문장 1 직접 수정/ }).first().fill("궤도 틀림 진행 속도를 추정해 보수 우선순위를 산정하고 현장에 적용함.");
  await page.getByRole("button", { name: "새 버전으로 저장" }).click();
  await expect(page).toHaveURL(new RegExp(`/runs/${id}/draft$`));
  await subnav(page, "버전·비교").click();
  await expect(page.locator("ins.diff-ins").first()).toBeVisible();
  await shot(page, 8, "versions");
  await subnav(page, "최종 검토").click();
  await page.getByRole("button", { name: "최종 검토 요청" }).click();
  await expect(page.getByRole("heading", { name: /Argon 최종 검토/ })).toBeVisible({ timeout: 30_000 });
  await shot(page, 9, "final-review");
  await subnav(page, "최종 마무리").click();
  await expect(page.getByRole("radio", { name: "응용연구" })).toBeChecked();
  await shot(page, 10, "finalize");
  await page.getByRole("link", { name: "run 목록" }).click();
  await expect(page.getByRole("table")).toBeVisible();
  await shot(page, 11, "runs");
  await page.getByRole("link", { name: "자료 검색" }).click();
  await page.getByLabel("검색어").fill("궤도");
  await page.getByRole("button", { name: "검색" }).click();
  await expect(page.getByText("비신뢰").first()).toBeVisible();
  await shot(page, 12, "search");
  await page.getByRole("link", { name: "자료원 상태" }).click();
  await expect(page.getByText("알리오 공시 연구보고서")).toBeVisible();
  await shot(page, 13, "sources");
  // 다크 테마 + 폰 너비
  await page.getByRole("button", { name: /어두운 테마로 바꾸기/ }).click();
  await page.setViewportSize({ width: 360, height: 780 });
  await page.goto(`/runs/${id}/draft`);
  await expect(page.getByRole("heading", { name: "초안 본문" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
  await shot(page, 14, "draft-dark-360");
});
