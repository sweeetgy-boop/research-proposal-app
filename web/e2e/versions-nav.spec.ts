/** 레인 D 항목 21·22·25 (가짜 백엔드) — 그림 확인함은 버전을 만들지 않는다, 초안 보기 [수정 없이 최종 검토로],
 *  아래 이동 막대로 모든 단계 이동, 모든 화면에 "run" 낱말이 보이지 않는다. */
import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { expectNoRunWord, fillIdea, login, subnav, mainNav } from "./helpers";

const SHOTS = process.env.VERSIONS_NAV_SCREENS ?? ""; // 캡처 폴더 (비면 찍지 않는다)

async function shot(page: Page, name: string) {
  if (!SHOTS) return;
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `2026-10-28-versions-nav-${name}.png`), fullPage: false });
}

const bar = (page: Page) => page.getByRole("navigation", { name: "단계 이동" });
const next = (page: Page) => bar(page).getByTestId("stepnav-next");
const prev = (page: Page) => bar(page).getByTestId("stepnav-prev");

/** ①→②→브리핑→③ 을 아래 막대로 지나며 화면마다 "run" 이 없는지 본다. run id 를 돌려준다. */
async function createRunViaBar(page: Page): Promise<string> {
  await expect(bar(page)).toBeVisible();
  await expectNoRunWord(page);
  await fillIdea(page);
  await bar(page).getByRole("button", { name: "다음: 유사과제 확인" }).click();
  await expect(page).toHaveURL(/\/new\/precheck$/);
  await expect(bar(page).getByRole("button", { name: "다음: 선행연구 브리핑" })).toBeVisible();
  await expectNoRunWord(page);
  await shot(page, "precheck-bar");
  await bar(page).getByRole("button", { name: "다음: 선행연구 브리핑" }).click();
  await expect(page).toHaveURL(/\/new\/brief$/);
  await expectNoRunWord(page);
  await next(page).click();
  await expect(page).toHaveURL(/\/new\/clarify$/);
  await expect(page.getByText(/질문을 준비하는 중/)).toHaveCount(0, { timeout: 30_000 });
  await expectNoRunWord(page);
  await page.getByRole("button", { name: /초안 생성 시작|답하고 생성 시작/ }).click();
  await expect(page).toHaveURL(/\/runs\/[0-9a-f-]+(\/draft)?$/, { timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "초안 본문" })).toBeVisible({ timeout: 30_000 });
  return /\/runs\/([0-9a-f-]+)/.exec(page.url())![1]!;
}

async function versionCount(page: Page, id: string): Promise<number> {
  const r = await page.request.get(`/v1/runs/${id}/versions`);
  expect(r.ok()).toBeTruthy();
  return ((await r.json()) as { versions: unknown[] }).versions.length;
}

test("그림 확인함 3회 뒤에도 버전 수 그대로 · 확인 n건 · 버전 목록에 확인 기록", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await login(page);
  const id = await createRunViaBar(page);
  await subnav(page, "직접 수정").click();
  await expect(page).toHaveURL(new RegExp(`/runs/${id}/edit$`));
  const before = await versionCount(page, id);
  for (let i = 0; i < 3; i++) {
    const btn = page.getByRole("button", { name: / 확인함$/ }).first();
    await expect(btn).toBeVisible();
    await btn.click();
    await expect(page.getByText("확인 표시를 저장했습니다 (새 버전 없음)").first()).toBeVisible();
    await expect(page.getByRole("button", { name: / 확인함$/ })).toHaveCount(2 - i);
  }
  expect(await versionCount(page, id)).toBe(before);
  await expect(page.getByTestId("change-count")).toHaveText("변경 0건");
  await expect(page.getByTestId("confirm-count")).toContainText("확인 3건");
  await shot(page, "edit-confirms");
  await expectNoRunWord(page);
  await subnav(page, "버전·비교").click();
  await expect(page.getByRole("heading", { name: new RegExp(`버전 ${before}개`) })).toBeVisible();
  await expect(page.getByText("Argon 작성").or(page.getByText("로컬 작성")).first()).toBeVisible();
  await expect(page.getByText(/^확인 3건$/)).toBeVisible();
  await expect(page.getByText(/그림 confirm/)).toHaveCount(0);
  await shot(page, "versions");
  await expectNoRunWord(page);
});

test("초안 보기 → [수정 없이 최종 검토로] → 아래 막대로 ①~⑥ 모두 이동", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await login(page);
  const id = await createRunViaBar(page);
  await subnav(page, "초안 보기").click();
  await expectNoRunWord(page);
  await shot(page, "draft-bar");

  await page.getByRole("button", { name: "수정 없이 최종 검토로" }).click();
  const ask = page.getByRole("dialog");
  await expect(ask.getByText("변경된 내용이 없습니다. 최종 검토로 넘어갈까요?")).toBeVisible();
  await ask.getByRole("button", { name: "확인" }).click();
  await expect(page).toHaveURL(new RegExp(`/runs/${id}/final-review$`));
  await expectNoRunWord(page);

  // ⑤ 에서 ⑥ 은 아직 막힘(이유), 최종 검토를 받으면 열린다
  await expect(bar(page).getByRole("button", { name: "다음: 최종 마무리" })).toBeDisabled();
  await page.getByRole("button", { name: "최종 검토 요청" }).click();
  await expect(page.getByRole("heading", { name: /Argon 최종 검토/ })).toBeVisible({ timeout: 30_000 });
  await expect(bar(page).getByRole("button", { name: "다음: 최종 마무리" })).toBeEnabled();
  await next(page).click();
  await expect(page).toHaveURL(new RegExp(`/runs/${id}/finalize$`));
  await expect(next(page)).toHaveCount(0); // ⑥ 이 마지막
  await expectNoRunWord(page);

  // 뒤로: ⑥ → ⑤ → ④ → ③ → ② → ①, 위쪽 단계 표시·탭과 같은 단계
  const steps = page.getByRole("navigation", { name: "작성 단계" });
  const back: [RegExp, RegExp][] = [
    [/\/final-review$/, /5단계 진행 중/],
    [/\/edit$/, /4단계 진행 중/],
    [/\/draft$/, /3단계 진행 중/],
    [/\/precheck$/, /2단계 진행 중/],
    [/\/idea$/, /1단계 진행 중/],
  ];
  for (const [url, step] of back) {
    await prev(page).click();
    await expect(page).toHaveURL(new RegExp(`/runs/${id}${url.source}`));
    await expect(steps.getByRole("link", { name: step })).toHaveAttribute("aria-current", "step");
    await expectNoRunWord(page);
  }
  await expect(prev(page)).toHaveCount(0); // ① 이 처음
  // 앞으로: ① → ② → ③ → ④
  for (const url of [/\/precheck$/, /\/draft$/, /\/edit$/]) {
    await next(page).click();
    await expect(page).toHaveURL(new RegExp(`/runs/${id}${url.source}`));
  }
  await expect(subnav(page, "직접 수정")).toHaveAttribute("aria-current", "page");
  // 막대가 본문을 가리지 않는다 — 편집 저장 막대는 이동 막대 위에 붙는다
  const save = page.getByRole("button", { name: "새 버전으로 저장" });
  await save.scrollIntoViewIfNeeded();
  const saveBox = (await save.boundingBox())!;
  const barBox = (await bar(page).boundingBox())!;
  expect(saveBox.y + saveBox.height).toBeLessThanOrEqual(barBox.y + 1);

  // 목록 화면도 "run" 없이
  await mainNav(page).getByRole("link", { name: /내 제안서/ }).click();
  await expect(page.getByRole("heading", { name: "내 제안서" })).toBeVisible();
  await expectNoRunWord(page);
});
