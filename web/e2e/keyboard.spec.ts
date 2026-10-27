import { expect, test } from "@playwright/test";
import { TOKEN, login, subnav } from "./helpers";

test("키보드만으로 로그인 → 입력 → 유사과제 확인 → 다음", async ({ page }) => {
  await page.goto("/login");
  // 건너뛰기 링크: 포커스되면 화면에 보이고, Enter 로 본문(main)에 포커스가 간다
  const skip = page.getByRole("link", { name: "본문으로 건너뛰기" });
  await skip.focus();
  await expect(skip).toBeFocused();
  const box = await skip.boundingBox();
  expect(box && box.y >= 0).toBe(true);
  await page.keyboard.press("Enter");
  expect(await page.evaluate(() => document.activeElement?.id)).toBe("main");
  await page.getByRole("button", { name: "관리자" }).focus();
  await page.keyboard.press("Enter");
  await page.getByLabel("관리자 접속 토큰").focus();
  await page.keyboard.type(TOKEN);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/new$/);

  // 입력 방식 라디오: 화살표로 상세 입력(4칸) 선택
  await page.getByRole("radio", { name: "간편 입력" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("radio", { name: "상세 입력(4칸)" })).toBeChecked();

  await page.getByLabel(/현재 상황·문제/).focus();
  await page.keyboard.type("궤도 틀림이 반복 발생함");
  await page.keyboard.press("Tab");
  await page.keyboard.type("다짐 효과가 오래 가지 않음");
  await page.keyboard.press("Tab");
  await page.keyboard.type("주기적 보수로는 진행 속도를 반영하지 못함");
  await page.keyboard.press("Tab");
  await page.keyboard.type("검측 이력 기반 보수 우선순위 산정");
  // 제출 버튼까지 Tab 으로 이동해 Enter
  for (let i = 0; i < 20; i++) {
    const name = await page.evaluate(() => document.activeElement?.textContent ?? "");
    if (name.includes("유사과제 확인")) break;
    await page.keyboard.press("Tab");
  }
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/precheck/);

  // 포커스 링이 보이는지: 포커스된 요소의 outline 이 none 이 아니어야 한다
  await page.getByRole("button", { name: /다음: 선행연구 브리핑/ }).focus();
  const outline = await page.evaluate(() => getComputedStyle(document.activeElement as Element).outlineStyle);
  expect(outline).not.toBe("none");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/brief/);
  await page.getByRole("button", { name: /다음: 보강 질문/ }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/clarify/);

  // 대화상자: 버전 화면 복원 확인창은 Esc 로 닫힌다 — 여기서는 테마 토글로 키보드 조작만 확인
  await page.getByRole("button", { name: /테마로 바꾸기/ }).focus();
  await page.keyboard.press("Enter");
  expect(await page.evaluate(() => document.documentElement.getAttribute("data-theme"))).toMatch(/dark|light/);
});

test("Esc 로 대화상자 닫기 (버전 복원 확인창)", async ({ page }) => {
  await login(page);
  await page.goto("/runs");
  await page.getByRole("table").or(page.getByText("아직 run 이 없습니다")).waitFor();
  const first = page.getByRole("link", { name: /^\d{14}-\d{8}$/ }).first();
  test.skip((await first.count()) === 0, "앞 테스트가 만든 run 이 필요");
  await first.click();
  await subnav(page, "버전·비교").click();
  const restore = page.getByRole("button", { name: /v1 으로 복원/ });
  await page.getByRole("heading", { name: /버전 \d+개/ }).waitFor();
  test.skip((await restore.count()) === 0 || !(await restore.isEnabled()), "복원 가능한 상태가 아님");
  await restore.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});
