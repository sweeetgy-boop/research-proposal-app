/** 화면 캡처 — 빈 초안 금지(ADR 0027): 실패 섹션 "이 섹션 다시 생성" 버튼·대체 작성 배지.
 *  가짜 백엔드(RRA_FAKE_LLM=1)는 실패를 내지 않으므로 /draft 응답만 가로채 실패·대체 섹션을 끼워 넣는다.
 *  RRA_SCREENS_DIR 가 없으면 건너뛴다 (CI 에서는 돌지 않는다). */
import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { createRun, login } from "./helpers";

const OUT = process.env.RRA_SCREENS_DIR ?? "";
test.skip(!OUT, "RRA_SCREENS_DIR 가 없으면 건너뜀");

test("실패 섹션 버튼·대체 작성 배지", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await login(page);
  const id = await createRun(page);
  await page.route(`**/v1/runs/${id}/draft`, async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    body.sections = body.sections.map((s: { key: string }) => (s.key === "expected_standing" ? { ...s, sentences: [] } : s));
    body.failed_sections = [{ key: "expected_standing", reason: "json", label: "JSON 문법 오류(잘린 응답 포함)" }];
    body.fallback_sections = [{ key: "tech_importance", provider: "gemini", model: "gemini-4-argon", reason: "empty" }];
    body.problems = [
      ...body.problems,
      { section: "expected_standing", code: "generation_failed", severity: "warning", message: "생성 실패(JSON 문법 오류(잘린 응답 포함)) — 이 섹션을 다시 생성하십시오", sentence: null },
    ];
    await route.fulfill({ response: res, json: body });
  });
  await page.goto(`/runs/${id}/draft`);
  await expect(page.getByRole("button", { name: /이 섹션 다시 생성/ })).toBeVisible();
  await expect(page.getByText("대체 작성")).toBeVisible();
  fs.mkdirSync(OUT, { recursive: true });
  await page.screenshot({ path: path.join(OUT, "2026-10-28-feat-draft-fallback-01-failed-and-fallback.png"), fullPage: true });
  await page.getByRole("button", { name: /이 섹션 다시 생성/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("button", { name: /반영/ })).toBeVisible({ timeout: 30_000 });
  await page.screenshot({ path: path.join(OUT, "2026-10-28-feat-draft-fallback-02-regenerate-dialog.png"), fullPage: true });
});
