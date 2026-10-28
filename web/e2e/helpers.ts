import { expect, type Page } from "@playwright/test";

export const TOKEN = process.env.RRA_E2E_TOKEN ?? "e2e-token-1234";
/** 가짜 모드(adapters/fake/auth.py)의 고정 계정 — e2e 전용 */
export const STAFF_NO = "E2E-0001";
export const GUEST = { id: "e2e", password: "e2e-password-1" };

/** 관리자 토큰 로그인 — "관리자" 링크 아래 토큰 칸 */
export async function login(page: Page) {
  await page.goto("/login");
  await page.getByRole("button", { name: "관리자" }).click();
  await page.getByLabel("관리자 접속 토큰").fill(TOKEN);
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).toHaveURL(/\/new$/);
}

export async function loginStaff(page: Page, staffNo = STAFF_NO) {
  await page.goto("/login");
  await page.getByRole("tab", { name: "철도연구원 직원(사번)" }).click();
  await page.getByLabel("사번", { exact: true }).fill(staffNo);
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).toHaveURL(/\/new$/);
}

export async function loginGuest(page: Page, id = GUEST.id, password = GUEST.password) {
  await page.goto("/login");
  await page.getByRole("tab", { name: "그 외 사용자(아이디·비밀번호)" }).click();
  await page.getByLabel("아이디", { exact: true }).fill(id);
  await page.getByLabel("비밀번호", { exact: true }).fill(password);
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).toHaveURL(/\/new$/);
}

/** ① 입력 방식을 상세(4칸)로 — 기본은 간편 입력 */
export async function detailMode(page: Page) {
  const radio = page.getByRole("radio", { name: "상세 입력(4칸)" });
  if (!(await radio.isChecked())) await radio.check({ force: true });
  await expect(page.getByLabel(/현재 상황·문제/)).toBeVisible();
}

export async function fillIdea(page: Page, suffix = "") {
  await detailMode(page);
  await page.getByLabel(/현재 상황·문제/).fill(`궤도 틀림이 반복 발생함${suffix}`);
  await page.getByLabel(/발생 원인/).fill("다짐 효과가 오래 가지 않음");
  await page.getByLabel(/현행 대응의 한계/).fill("주기적 보수로는 진행 속도를 반영하지 못함");
  await page.getByLabel(/해결 목표/).fill("검측 이력 기반 보수 우선순위 산정");
}

/** ①→②→③ 을 지나 run 이 drafted 가 될 때까지. run id 를 돌려준다. */
export async function createRun(page: Page): Promise<string> {
  await fillIdea(page);
  await page.getByRole("button", { name: "유사과제 확인" }).click();
  await expect(page).toHaveURL(/\/new\/precheck$/);
  await page.getByRole("button", { name: /다음: 선행연구 브리핑/ }).click();
  await expect(page).toHaveURL(/\/new\/brief$/);
  await page.getByRole("button", { name: /다음: 보강 질문/ }).click();
  await expect(page).toHaveURL(/\/new\/clarify$/);
  await page.getByRole("button", { name: /초안 생성 시작|답하고 생성 시작/ }).click();
  await expect(page).toHaveURL(/\/runs\/[0-9a-f-]+(\/draft)?$/, { timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "초안 본문" })).toBeVisible({ timeout: 30_000 });
  const m = /\/runs\/([0-9a-f-]+)/.exec(page.url());
  return m![1]!;
}

/** run 하위 메뉴(진행·초안 보기·직접 수정·버전·비교·최종 검토·최종 마무리) 링크 */
export function subnav(page: Page, name: string) {
  return page.getByRole("navigation", { name: "run 하위 메뉴" }).getByRole("link", { name });
}
