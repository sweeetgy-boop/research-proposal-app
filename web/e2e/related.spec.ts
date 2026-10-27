/** ② 관련 연구(참고) — 가짜 백엔드의 scienceon:fake-1(논문)은 유사과제 판정 표가 아니라 "관련 연구" 목록에만 보인다 (ADR 0028).
 *  RRA_SCREENS_DIR 가 있으면 캡처한다 (docs/screens/25-related-research.png). */
import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fillIdea, login } from "./helpers";

const OUT = process.env.RRA_SCREENS_DIR ?? "";

test("논문은 유사과제 판정이 아니라 '관련 연구' 참고 목록에 보인다", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  await login(page);
  await fillIdea(page);
  await page.getByRole("button", { name: "유사과제 확인" }).click();
  await expect(page).toHaveURL(/\/new\/precheck$/);

  // 판정 표에는 과제형 자료원만 — 논문은 없다
  const table = page.getByRole("table", { name: "유사과제 목록" });
  await expect(table).toBeVisible();
  await expect(table.getByText("궤도 틀림 진행 속도 추정 논문 (가짜)")).toHaveCount(0);

  // 관련 연구 목록: 배지 "참고", 출처·연도·유사도, 원문 링크(새 창 + noopener)
  const section = page.getByRole("region", { name: /관련 연구 1건/ });
  await expect(section.getByText("궤도 틀림 진행 속도 추정 논문 (가짜)")).toBeVisible();
  await expect(section.getByText("참고", { exact: true })).toBeVisible();
  await expect(section.getByText(/ScienceON 국내 논문·보고서 · 논문 · 2024 · 유사도 0\.\d{3}/)).toBeVisible();
  await expect(section.getByText("차단", { exact: true })).toHaveCount(0);
  const link = section.getByRole("link", { name: /원문/ });
  await expect(link).toHaveAttribute("href", "https://scienceon.kisti.re.kr/fake-1");
  await expect(link).toHaveAttribute("rel", "noopener noreferrer");
  await expect(link).toHaveAttribute("target", "_blank");

  if (OUT) {
    fs.mkdirSync(OUT, { recursive: true });
    await section.scrollIntoViewIfNeeded();
    await section.screenshot({ path: path.join(OUT, "25-related-research.png") });
  }
  await expect(page.getByRole("button", { name: /다음: 선행연구 브리핑/ })).toBeEnabled();
  expect(errors).toEqual([]);
});
