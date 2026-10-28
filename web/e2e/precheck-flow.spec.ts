import { expect, test } from "@playwright/test";
import { fillIdea, login } from "./helpers";

// ② 유사과제 흐름 (레인 A, 가짜 모드): AI 같음 판정 차단 → [관련 없음]·[유사함] → 비교표 → 과제안 고르기·직접 고치기 → 다음
test("② 유사함·관련 없음 선택 → 비교표 → 과제안 고르기·수정 → 다음", async ({ page }) => {
  await login(page);
  await fillIdea(page, " (중복)"); // 가짜 Argon 이 첫 후보를 '같다' 로 판정 → 차단
  await page.getByRole("button", { name: "유사과제 확인" }).click();
  await expect(page).toHaveURL(/\/new\/precheck$/);

  const next = page.getByRole("button", { name: /다음: 선행연구 브리핑/ });
  await expect(page.getByText("같다").first()).toBeVisible();
  await expect(next).toBeDisabled();
  await expect(page.getByText(/차단 경보를 확인해 주세요/)).toBeVisible();
  await expect(page.getByText("유사한 과제를 고르면 비교표가 만들어집니다")).toBeVisible();

  const table = page.getByRole("table", { name: /유사과제 목록/ });
  const rows = table.locator("tbody tr");
  const blocked = rows.filter({ has: page.getByText("차단", { exact: true }) }).first();
  await blocked.getByRole("button", { name: "관련 없음" }).click();
  await expect(next).toBeEnabled();
  await expect(page.getByText(/차단 경보를 풀었습니다/)).toBeVisible();

  const other = rows.filter({ hasNot: page.getByText("차단 해제") }).first();
  await other.getByRole("button", { name: "유사함" }).click();
  await page.getByRole("button", { name: "선택 적용" }).click(); // v3: 선택은 [선택 적용] 으로 반영 (ADR 0039)
  const compare = page.getByRole("table", { name: /차별성 비교표/ });
  await expect(compare).toBeVisible();
  await expect(compare.getByText("제안 과제")).toBeVisible();

  // 과제안 고르기 → 직접 고치기 → [AI로 다듬기] → 확정
  await page.getByRole("button", { name: "이 안으로 진행" }).first().click();
  await expect(page.getByText(/과제안 1번을 입력에 반영했습니다/).first()).toBeVisible();
  await page.getByRole("button", { name: "직접 작성" }).first().click();
  const method = page.getByLabel("연구방법", { exact: true });
  await method.fill("검측 이력 분석");
  await page.getByRole("button", { name: "연구방법 AI로 다듬기" }).click();
  await expect(method).toHaveValue("검측 이력 분석 방안을 마련함");
  await page.getByRole("button", { name: "이 내용으로 확정" }).click();
  await expect(page.getByText(/고친 과제안을 입력에 반영했습니다/).first()).toBeVisible();
  await expect(compare.getByText("검측 이력 분석 방안을 마련함")).toBeVisible(); // 비교표 제안 행이 바뀐다

  const dir = process.env.RRA_SCREENS_DIR;
  if (dir) await page.screenshot({ path: `${dir}/precheck-flow.png`, fullPage: true });
  await next.click();
  await expect(page).toHaveURL(/\/new\/brief$/);
});
