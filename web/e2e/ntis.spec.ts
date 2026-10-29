/** ② NTIS 과제 카드 — 가짜 백엔드가 national_rnd 알림(ntis:fake-1)과 /v1/precheck/ntis-outcomes 더미를 낸다.
 *  RRA_SCREENS_DIR 가 있으면 블록을 캡처한다 (docs/history/screens/2026-10-27-web-ntis-01-precheck.png). */
import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fillIdea, login, goPrecheck } from "./helpers";

const OUT = process.env.RRA_SCREENS_DIR ?? "";

test("유사과제 확인에 국가R&D 과제 라벨·주요 성과(참고용)·NTIS 추천(외부 링크)이 보인다", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  await login(page);
  await fillIdea(page);
  await goPrecheck(page);
  await expect(page).toHaveURL(/\/new\/precheck$/);

  // 알림 표의 티어 라벨
  const table = page.getByRole("table", { name: "유사과제 목록" });
  await expect(table.getByRole("cell", { name: "국가R&D 과제", exact: true })).toBeVisible();

  // 과제 카드: 주요 성과(참고용) — 논문·특허
  const section = page.getByRole("region", { name: "NTIS 과제 성과·추천" });
  await expect(section.getByRole("heading", { name: "NTIS 과제 성과·추천" })).toBeVisible();
  const card = section.getByTestId("ntis-project").first();
  await expect(card.getByText("주요 성과 (참고용)")).toBeVisible();
  await expect(card.getByText("궤도 틀림 진행 예측 모델 (가짜)")).toBeVisible();
  await expect(card.getByText("특허", { exact: true })).toBeVisible();

  // NTIS 추천: 외부 링크·미검증, 새 창 + noopener
  const rec = section.getByTestId("ntis-recommended");
  await expect(rec.getByRole("heading", { name: "NTIS 추천" })).toBeVisible();
  await expect(rec.getByText(/외부 링크 · 미검증/)).toBeVisible();
  const link = rec.getByRole("link").first();
  await expect(link).toHaveAttribute("href", /^https:\/\/www\.ntis\.go\.kr\//);
  await expect(link).toHaveAttribute("rel", "noopener noreferrer");
  await expect(link).toHaveAttribute("target", "_blank");
  await expect(section.getByText(/지시가 아닙니다/)).toBeVisible(); // notice 캡션

  if (OUT) {
    fs.mkdirSync(OUT, { recursive: true });
    await section.scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(OUT, "2026-10-27-web-ntis-01-precheck.png"), fullPage: true });
  }
  // 다음 단계는 NTIS 결과와 무관하게 열려 있다
  await expect(page.getByRole("button", { name: /다음: 선행연구 브리핑/ })).toBeEnabled();
  expect(errors).toEqual([]);
});
