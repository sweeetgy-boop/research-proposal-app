import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { createRun, fillIdea, login, policyPopup, subnav } from "./helpers";
import { expectNoInternalIds } from "./helpers-text";

/** RRA_SCREENS_DIR 가 있으면 화면을 캡처한다 (docs/history/screens/2026-10-28-feat-policy-l2-NN-*.png) */
const OUT = process.env.RRA_SCREENS_DIR ?? "";
async function shot(page: Page, n: number, name: string) {
  if (!OUT) return;
  fs.mkdirSync(OUT, { recursive: true });
  await page.screenshot({ path: path.join(OUT, `2026-10-28-feat-policy-l2-${String(n).padStart(2, "0")}-${name}.png`), fullPage: true });
}

// 레인 B (ADR 0040) — 가짜 모드: ① 정책 근거 추천은 정책 자료만(연구용역 사내 발주 제외),
// L2 로컬 검토: 불일치 문장의 Argon 제안 [무시](버전 그대로)·[반영](새 버전), 화면에 내부 번호 없음.
test("정책 근거 추천에 연구용역(사내 발주) 문서가 나오지 않고, 번호 없이 제목·자료원 이름", async ({ page }) => {
  await login(page);
  await fillIdea(page, " (정책 추천)");
  // 정책 근거 칸 아래 [정책 근거 추천 열기] → 팝업 (ADR 0052)
  await page.getByRole("button", { name: "정책 근거 추천 열기" }).click();
  const list = policyPopup(page).getByRole("list", { name: "정책 근거 추천 목록" });
  await expect(list).toBeVisible();
  await expect(list.getByRole("button", { name: /철도 안전 강화 계획 \(가짜\) · 국토교통부 근거 보기/ })).toBeVisible();
  await expect(list.getByText(/가짜 연구용역/)).toHaveCount(0);
  await expect(list.getByRole("link", { name: /원문/ }).first()).toBeVisible();
  await expect(list).not.toContainText("https://");
  await expectNoInternalIds(page);
  await shot(page, 1, "policy-suggestions");
  // 문서 칩을 누르면 근거 패널(요약 + 원문 링크)
  await list.getByRole("button", { name: /철도 안전 강화 계획 \(가짜\)/ }).click();
  const panel = page.getByRole("dialog", { name: "철도 안전 강화 계획 (가짜)" });
  await expect(panel.getByRole("link", { name: /원문/ })).toBeVisible();
  await expectNoInternalIds(page, panel);
  await panel.getByRole("button", { name: "닫기" }).last().click();
});

test("로컬 검토 불일치 문장의 Argon 제안 — [무시]는 버전 그대로, [반영]은 새 버전", async ({ page }) => {
  await login(page);
  const first = await createRun(page);
  // 초안 화면: 문장 옆 "로컬 검토: …", 불일치 문장 아래 제안 카드 (자동 반영 없음)
  await expect(page.getByTestId("local-review-summary")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("로컬 검토: 불일치").first()).toBeVisible();
  await expect(page.getByText("로컬 검토: 부분").first()).toBeVisible();
  const card = page.getByTestId("local-suggestion").first();
  await expect(card.getByText("근거 안에서 다시 쓰기")).toBeVisible();
  await expectNoInternalIds(page);
  await page.setViewportSize({ width: 1280, height: 900 });
  await shot(page, 2, "draft-local-review");

  // 근거 칩 → 근거 패널: 번호 대신 제목·자료원 이름
  await page.getByRole("button", { name: /근거 보기/ }).first().click();
  const ev = page.getByRole("dialog", { name: "근거 보기" });
  await expect(ev).toBeVisible();
  await expectNoInternalIds(page, ev);
  await ev.getByRole("button", { name: "닫기" }).last().click();

  // 제출 전 점검: 근거 확인에 "로컬 검토 불일치 1문장"
  await subnav(page, "제출 전 점검").click();
  await expect(page.getByText(/로컬 검토 불일치 1문장/)).toBeVisible();
  await expectNoInternalIds(page);
  await shot(page, 3, "submit-check");

  // [무시] — 결정 기록, 새 버전 없음
  await subnav(page, "초안 보기").click();
  const tabBefore = await page.getByRole("tab", { name: /^현재 v\d+$/ }).innerText();
  await page.getByRole("button", { name: "로컬 검토 제안 무시" }).first().click();
  await expect(page.getByText("무시함").first()).toBeVisible();
  await expect(page.getByRole("tab", { name: /^현재 v\d+$/ })).toHaveText(tabBefore);
  expect(first).toBeTruthy();

  // 다른 run: 직접 수정 화면에서 [반영] → 새 버전
  await page.goto("/new");
  await createRun(page);
  await subnav(page, "직접 수정").click();
  await expect(page.getByText("로컬 검토: 불일치").first()).toBeVisible();
  await expectNoInternalIds(page);
  await shot(page, 4, "edit-local-review");
  await page.getByRole("button", { name: "로컬 검토 제안 반영" }).first().click();
  await expect(page.getByText(/로컬 검토 제안을 v\d+ 으로 반영했습니다/).first()).toBeVisible();
  await expect(page.getByText("선행연구는 틀림 진행 속도를 직접 분석하지 않은 것으로 보임.").first()).toBeVisible();
});
