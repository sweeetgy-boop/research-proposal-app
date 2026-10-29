/** 레인 D — 과제 제목 머리, 위쪽 단계 표시로 이동, ① 입력 변경 → 관련 섹션만 다시 쓰기, 제출 전 점검
 *  (근거 일괄 승인·선택형 확정), 마무리 파일 이름 "<과제 제목>_v<번호>.hwpx" (가짜 백엔드). */
import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { createRun, login, subnav } from "./helpers";

const SHOTS = process.env.FORMAT_UI_SCREENS ?? ""; // 캡처 폴더 (비면 찍지 않는다)

async function shot(page: Page, name: string) {
  if (!SHOTS) return;
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `2026-10-28-format-ui-${name}.png`), fullPage: true });
}

function steps(page: Page) {
  return page.getByRole("navigation", { name: "작성 단계" });
}

test("단계 표시 이동 → 입력 변경 다시 쓰기 → 제출 전 점검 → 마무리 (파일 이름에 과제 제목)", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await login(page);
  const id = await createRun(page);

  // 항목 2 — 머리에 과제 제목, run 번호는 작게
  const titleEl = page.getByTestId("run-title");
  await expect(titleEl).not.toHaveText("제목 미정");
  const title = (await titleEl.textContent())?.trim() ?? "";
  expect(title.length).toBeGreaterThan(2);
  await expect(page.getByText(id, { exact: true })).toBeVisible();

  // 항목 17 — ⑥ 은 최종 검토 전이라 못 연다(이유), ④ 를 누르면 직접 수정 탭
  const finalize = steps(page).getByRole("link", { name: /최종 마무리/ });
  await expect(finalize).toHaveAttribute("aria-disabled", "true");
  await finalize.focus();
  await expect(page.getByRole("tooltip").filter({ hasText: "최종 검토 후 열립니다" })).toBeVisible();
  await shot(page, "stepper");
  await steps(page).getByRole("link", { name: /직접 수정/ }).click();
  await expect(page).toHaveURL(new RegExp(`/runs/${id}/edit$`));
  await expect(subnav(page, "직접 수정")).toHaveAttribute("aria-current", "page");

  // ① 을 run 안에서 열어 제약을 고치고 저장 → 관련 섹션만 다시 쓰기(새 버전)
  await steps(page).getByRole("link", { name: /아이디어 입력/ }).click();
  await expect(page).toHaveURL(new RegExp(`/runs/${id}/idea$`));
  await expect(page.getByLabel(/현재 상황·문제/)).toHaveValue(/궤도 틀림/);
  await page.getByText("선택 입력 (가제·제약·부서·예산)").click();
  await page.getByLabel(/예산·기간·현장 제약/).fill("연구기간 1년, 예산 1억 원 이내");
  await page.getByRole("button", { name: "입력 저장" }).click();
  const dialog = page.getByRole("dialog", { name: "바뀐 입력을 초안에 반영할까요?" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("제약 조건")).toBeVisible();
  await shot(page, "change-dialog");
  await dialog.getByRole("button", { name: "바뀐 내용과 관련된 섹션만 다시 쓰기(새 버전)" }).click();
  await expect(page).toHaveURL(new RegExp(`/runs/${id}/draft$`), { timeout: 30_000 });
  await expect(page.getByText(/새 버전 v\d+:/).first()).toBeVisible();

  // ⑤ 최종 검토 (단계 표시로)
  await steps(page).getByRole("link", { name: /최종 검토/ }).click();
  await expect(page).toHaveURL(new RegExp(`/runs/${id}/final-review$`));
  await page.getByRole("button", { name: "최종 검토 요청" }).click();
  await expect(page.getByRole("heading", { name: /Argon 최종 검토/ })).toBeVisible({ timeout: 30_000 });

  // 제출 전 점검 — 코드 대신 한국어, 근거 일괄 승인·제안값 확정
  await subnav(page, "제출 전 점검").click();
  await expect(page.getByRole("heading", { name: "제출 전 점검" })).toBeVisible();
  await expect(page.getByText("근거 확인", { exact: true })).toBeVisible();
  const bulk = page.getByRole("button", { name: /^근거 일괄 승인/ });
  if (await bulk.isEnabled()) {
    await bulk.click();
    await expect(page.getByText(/근거 \d+건을 승인했습니다/).first()).toBeVisible();
  }
  const accept = page.getByRole("button", { name: "제안값 그대로 확정" });
  while ((await accept.count()) > 0 && (await accept.first().isEnabled())) {
    await accept.first().click();
    await expect(page.getByText(/로 확정했습니다/).first()).toBeVisible();
    await page.waitForTimeout(300);
  }
  await expect(page.getByText("전체 경과(사람 작업 포함)")).toBeVisible();
  const body = (await page.locator("main").textContent()) ?? "";
  expect(body).not.toMatch(/input_missing|self_review|no_relevant_evidence|warning|sections_sum/);
  await shot(page, "submit-check");

  // ⑥ 최종 마무리 (단계 표시가 이제 열림) → 파일 이름
  await steps(page).getByRole("link", { name: /최종 마무리/ }).click();
  await expect(page).toHaveURL(new RegExp(`/runs/${id}/finalize$`));
  const downloadP = page.waitForEvent("download");
  await page.getByRole("button", { name: "HWPX 내려받기" }).click();
  const confirm = page.getByRole("dialog").getByRole("button", { name: "그대로 진행" });
  await confirm.click({ timeout: 3_000 }).catch(() => undefined);
  const download = await downloadP;
  const name = download.suggestedFilename();
  expect(name).toMatch(/_v\d+\.hwpx$/);
  expect(name).not.toMatch(/^proposal-/);
  expect(name.replace(/_v\d+\.hwpx$/, "")).toBe(title.replace(/[\\/:*?"<>|]/g, " ").replace(/\s+/g, " ").trim().slice(0, 60));
});
