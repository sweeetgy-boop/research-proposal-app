/** 연구 작업실(홈) — 로그인 전에는 히어로·시작 안내·로그인 카드만, 로그인 뒤 건수·최근 제안서 표(가짜 데이터),
 *  탭·제목 검색·정렬, 내 제안서 같은 줄 모양, 작성 가이드 (UI Research Studio 레인 2). */
import { expect, test, type Page } from "@playwright/test";
import { expectNoInternalIds } from "./helpers-text";
import { TOKEN, expectNoRunWord, login } from "./helpers";

const IDEAS = ["궤도 틀림이 반복 발생함", "전차선 마모 점검 주기가 길다"];

async function seedRuns(page: Page) {
  for (const s of IDEAS) {
    const r = await page.request.post("/v1/runs", {
      headers: { "X-RRA-Token": TOKEN },
      data: { current_state: s, root_cause: "다짐 효과가 오래 가지 않음", limitation: "주기적 보수로는 반영 못함", goal: "검측 이력 기반 우선순위" },
    });
    expect(r.status()).toBe(202);
  }
}

const rows = (page: Page) => page.getByTestId("run-rows").getByRole("listitem");

test("로그인 전 홈은 개인 데이터 없이, 로그인 뒤 건수·표가 채워진다", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Research Studio/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "제안서 작성, 이렇게 시작하세요" })).toBeVisible();
  // 본문만 본다 — 위쪽 통합 검색 팝업(닫힘)에도 "최근 제안서" 묶음 이름이 있다
  await expect(page.getByRole("main").getByText("연구 한눈에 보기")).toHaveCount(0);
  await expect(page.getByRole("main").getByText("최근 제안서")).toHaveCount(0);

  await seedRuns(page);
  await login(page);
  await page.goto("/");
  const all = page.getByTestId("overview-all");
  await expect(all).toContainText(/\d+\s*편/);
  const total = Number((await all.innerText()).match(/(\d+)\s*편/)![1]);
  expect(total).toBeGreaterThanOrEqual(2);
  await expect(rows(page).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("main").getByText("제안서는 연구원 서버에 저장됩니다.", { exact: true })).toBeVisible(); // 사이드바 아래에도 같은 안내
  await expect(page.getByRole("link", { name: /이어서 작성하기/ })).toBeVisible();
  await expectNoRunWord(page);
  await expectNoInternalIds(page);

  // 탭 — 같은 가짜 서버를 다른 시험도 쓰므로 건수는 탭 이름에서 읽는다
  const count = async (re: RegExp) => Number(((await page.getByRole("tab", { name: re }).innerText()).match(/(\d+)/) ?? ["", "0"])[1]);
  await page.getByRole("tab", { name: /^완료/ }).click();
  const done = await count(/^완료/);
  if (done === 0) await expect(page.getByText("조건에 맞는 제안서가 없습니다.")).toBeVisible();
  else await expect(rows(page).filter({ hasNotText: "마무리 완료" })).toHaveCount(0);
  await page.getByRole("tab", { name: /^완료/ }).press("ArrowLeft");
  await expect(page.getByRole("tab", { name: /^작성 중/ })).toHaveAttribute("aria-selected", "true");
  await expect(rows(page).filter({ hasText: "마무리 완료" })).toHaveCount(0);
  await page.getByRole("tab", { name: /^전체/ }).click();

  // 제목 검색·정렬
  await page.getByLabel("제안서 제목 검색").fill("없는제목zzz");
  await expect(page.getByText("조건에 맞는 제안서가 없습니다.")).toBeVisible();
  await page.getByLabel("제안서 제목 검색").fill("");
  await page.getByLabel("정렬").selectOption({ label: "제목순" });
  await expect(rows(page).first()).toBeVisible();
  await page.getByLabel("정렬").selectOption({ label: "진행률순" });
  await expect(rows(page).first()).toBeVisible();

  // ⋯ 메뉴 → 진행 상황
  await rows(page).first().getByRole("button", { name: /메뉴/ }).click();
  await page.getByRole("link", { name: "진행 상황" }).click();
  await expect(page).toHaveURL(/\/runs\/[0-9a-f-]+$/);

  // 전체 보기 → 내 제안서 (같은 줄 모양 + 작성 번호)
  await page.goto("/");
  await page.getByRole("link", { name: "전체 보기", exact: true }).click();
  await expect(page).toHaveURL(/\/runs$/);
  await expect(page.getByRole("heading", { level: 1, name: "내 제안서" })).toBeVisible();
  await expect(rows(page).first()).toBeVisible();
  await expectNoRunWord(page);
});

test("작성 가이드는 사용자용 네 부분을 보여 준다", async ({ page }) => {
  await page.goto("/guide");
  for (const name of ["사용 순서", "알려진 제약", "오류·개선점 기록 방법", "그림(인포그래픽) 안내"]) {
    await expect(page.getByRole("heading", { level: 2, name })).toBeVisible();
  }
  await page.getByRole("navigation", { name: "작성 가이드 목차" }).getByRole("link", { name: /알려진 제약/ }).click();
  await expect(page).toHaveURL(/#guide-limits$/);
  await expectNoRunWord(page);
});
