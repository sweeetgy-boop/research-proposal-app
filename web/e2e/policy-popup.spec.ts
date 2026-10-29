/** ① 정책 근거 추천 팝업과 나중에 다시 넣는 길 (ADR 0052) — 가짜 모드.
 *  간편 입력 → 나누기 → 보완 질문 답 → 팝업(1순위 미리 체크 + 추가 + 직접 입력) → [적용] → 초안 2-가-(1) 채워짐,
 *  [나중에 넣기] → 초안 → ④ [정책 근거 넣기] → 새 버전 2-가-(1) 채워짐, ⑥ 제출 전 점검 바로가기 → ④ 대화상자.
 *  실제 브라우저 axe(WCAG 2.x A/AA) 위반 0. RRA_SCREENS_DIR 가 있으면 화면을 캡처한다. */
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { createRun, login, policyPopup, subnav } from "./helpers";
import { expectNoInternalIds } from "./helpers-text";

const OUT = process.env.RRA_SCREENS_DIR ?? "";
async function shot(page: Page, n: number, name: string, target?: Locator | "viewport") {
  if (!OUT) return;
  fs.mkdirSync(OUT, { recursive: true });
  const file = path.join(OUT, `2026-10-29-feat-policy-popup-${String(n).padStart(2, "0")}-${name}.png`);
  if (target === "viewport") await page.screenshot({ path: file });
  else if (target) await target.screenshot({ path: file });
  else await page.screenshot({ path: file, fullPage: true });
}

// axe-core 를 페이지에 넣으려면 CSP(script-src 'self') 를 이 시험에서만 비켜 간다 — 앱 코드는 그대로
test.use({ bypassCSP: true });
const AXE = createRequire(import.meta.url).resolve("axe-core/axe.min.js");
async function expectNoAxe(page: Page, selector = "body") {
  // 화면 전환 애니메이션 중간 색을 대비로 재지 않도록 끝날 때까지 기다린다
  await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== "running"));
  await page.addScriptTag({ path: AXE });
  const violations = await page.evaluate(async (sel) => {
    const w = window as unknown as { axe: { run: (c: Element, o: unknown) => Promise<{ violations: { id: string; nodes: { html: string; failureSummary?: string }[] }[] }> } };
    const r = await w.axe.run(document.querySelector(sel)!, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } });
    return r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => `${n.html} — ${n.failureSummary ?? ""}`).join(" | ")}`);
  }, selector);
  expect(violations, violations.join("\n")).toEqual([]);
}

const POLICY_SENTENCE = "제안자가 적은 정책 근거에 부합하는 과제임."; // 가짜 LLM 의 2-가-(1) 문장 (정책 근거가 있을 때만)
const policySection = (page: Page) => page.locator("#sec-policy_importance");

test("간편 입력 → 보완 질문 답 → 팝업 [적용] → ② → 초안 2-가-(1) 이 채워진다", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await login(page);
  await page.getByLabel(/아이디어를 한두 문장으로/).fill("궤도 틀림이 반복 발생함. 검측 이력 기반으로 보수 우선순위를 정하고 싶음.");
  await page.getByRole("button", { name: "네 칸으로 나누기" }).click();
  await expect(page.getByRole("heading", { name: "네 칸 미리보기" })).toBeVisible({ timeout: 20_000 });
  await page.getByLabel(/그 문제가 생기는 원인은/).fill("다짐 효과가 오래 가지 않음");
  await page.getByLabel(/지금 하고 있는 대응/).fill("주기적 보수로는 진행 속도를 반영하지 못함");
  await page.getByRole("button", { name: "답 반영" }).click();
  await expect(page.getByText("모두 채워짐")).toBeVisible();
  await page.getByRole("button", { name: /상세 입력에 채우기/ }).click();

  // 팝업이 저절로 열리고 바로 추천을 받는다 — 1순위만 미리 체크("기본 추천"), 칸은 아직 비어 있다
  const popup = policyPopup(page);
  const list = popup.getByRole("list", { name: "정책 근거 추천 목록" });
  await expect(list).toBeVisible();
  const boxes = list.getByRole("checkbox");
  await expect(boxes.first()).toBeChecked();
  await expect(boxes.nth(1)).not.toBeChecked();
  await expect(popup.getByText("기본 추천", { exact: true })).toHaveCount(1);
  await expect(page.locator("#f-policy_basis")).toHaveValue("");
  await expect(list).not.toContainText("https://");
  await expectNoInternalIds(page, popup);
  await expectNoAxe(page, "dialog[open]");
  await shot(page, 1, "idea-popup", popup);

  await boxes.nth(1).check();
  await popup.getByLabel("직접 입력 (선택)").fill("제4차 철도안전 종합계획 — 노후 궤도 검측 고도화");
  await popup.getByRole("button", { name: /^적용/ }).click();
  await expect(popup).toBeHidden();
  const basis = await page.locator("#f-policy_basis").inputValue();
  expect(basis.split("\n")).toHaveLength(3);
  expect(basis).toContain("제4차 철도안전 종합계획 — 노후 궤도 검측 고도화");
  await shot(page, 2, "idea-policy-filled", page.getByTestId("policy-basis-box"));

  // 칸이 찼으니 [다음] 은 팝업 없이 ② 로
  await page.getByRole("button", { name: "다음: 유사과제 확인" }).click();
  await expect(page).toHaveURL(/\/new\/precheck$/);
  await page.getByRole("button", { name: /다음: 선행연구 브리핑/ }).click();
  await page.getByRole("button", { name: /다음: 보강 질문/ }).click();
  await expect(page.getByRole("button", { name: "정책적 중요도 작성안 보기" })).toBeVisible(); // 정책 근거가 있으면 접힌 채
  await page.getByRole("button", { name: /초안 생성 시작|답하고 생성 시작/ }).click();
  await expect(page.getByRole("heading", { name: "초안 본문" })).toBeVisible({ timeout: 30_000 });
  await expect(policySection(page)).toBeVisible();
  await expect(page.getByText(POLICY_SENTENCE).first()).toBeVisible();
  await expect(page.getByTestId("policy-empty-draft")).toHaveCount(0);
});

test("[나중에 넣기] → 초안 → ④ [정책 근거 넣기] → 새 버전에서 2-가-(1) 채워짐", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await login(page);
  await createRun(page); // ① [다음] 때 뜬 팝업은 [나중에 넣기] (helpers.goPrecheck)
  // ③ 초안 보기: 빈 2-가-(1) 자리에 바로가기
  const toEdit = page.getByRole("link", { name: "정책 근거 넣기 (④ 직접 수정)" });
  await expect(toEdit).toBeVisible();
  await shot(page, 3, "draft-policy-empty", policySection(page));

  await subnav(page, "직접 수정").click();
  const head = page.getByRole("button", { name: "정책 근거 넣기·바꾸기" });
  await expect(head).toBeVisible();
  const empty = page.getByTestId("policy-empty");
  await expect(empty).toContainText("정책 근거가 없습니다");
  await page.locator("h3", { hasText: "2-가-(1) 정책적 중요도" }).evaluate((el) => el.scrollIntoView({ block: "center" }));
  await shot(page, 4, "edit-policy-empty", "viewport");
  await expectNoAxe(page, "main");

  await empty.getByRole("button", { name: "정책 근거 넣기" }).click();
  const d = page.getByRole("dialog", { name: /정책 근거 넣기·바꾸기/ });
  await expect(d.getByLabel("직접 입력 (선택)")).toBeVisible();
  await expect(d.getByRole("list", { name: "정책적 중요도 작성안 목록" })).toBeVisible();
  await d.getByLabel("직접 입력 (선택)").fill("제4차 철도안전 종합계획의 노후 궤도 검측 고도화에 부합함");
  await expectNoAxe(page, "dialog[open]");
  await shot(page, 5, "edit-policy-dialog", d);
  await d.getByRole("button", { name: "이 안으로 — 정부 계획" }).click(); // 작성안 + 직접 입력이 함께
  await expect(page.getByText(/정책 근거를 v\d+ 으로 반영했습니다/).first()).toBeVisible();
  await expect(page.getByTestId("policy-empty")).toHaveCount(0);
  await expect(page.getByText("제4차 철도안전 종합계획의 노후 궤도 검측 고도화에 부합함").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "정책 근거 넣기·바꾸기" })).toBeVisible(); // 채운 뒤에도 바꾸기
});

test("⑥ 제출 전 점검 — [정책 근거] 항목의 [정책 근거 넣기] → ④ 대화상자가 열린다", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await login(page);
  const id = await createRun(page);
  await subnav(page, "제출 전 점검").click();
  const go = page.getByRole("list", { name: "제출 전 점검 항목" }).getByRole("button", { name: "정책 근거 넣기" });
  await expect(go).toBeVisible();
  await expectNoAxe(page, "main");
  await go.evaluate((el) => el.scrollIntoView({ block: "center" }));
  await shot(page, 6, "submit-check-policy", "viewport");
  await go.click();
  await expect(page).toHaveURL(new RegExp(`/runs/${id}/edit$`));
  await expect(page.getByRole("dialog", { name: /정책 근거 넣기·바꾸기/ })).toBeVisible();
});
