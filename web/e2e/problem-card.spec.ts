import path from "node:path";
import { expect, test, type Page, type Request } from "@playwright/test";
import { expectNoRunWord, fillIdea, goPrecheck, login } from "./helpers";
import { expectNoInternalIds } from "./helpers-text";
import { REAL_CARD, DIAGNOSE_OFF, problemCard, stubProblemCard } from "./helpers-problem-card";

// ① '핵심 문제' 카드 (ADR 0065, 계약 docs/contracts/problem-card.md 5절). 진단·수정 두 경로는 helpers-problem-card.ts 가
// 계약 형식 응답으로 가로챈다(서버는 레인 A) — 나머지(유사과제 확인·과제안·초안 생성)는 가짜 모드 서버 그대로다.
// 과제안·초안 요청에 실린 카드는 실제 서버의 입력 검증을 지난다(스위치가 꺼져 있어 서버는 받은 카드를 쓰지 않는다).

const OUT = process.env.RRA_SCREENS_DIR ?? "";
const shot = async (page: Page, name: string) => {
  if (OUT) await page.screenshot({ path: path.join(OUT, `2026-11-10-problem-card-${name}.png`), fullPage: true });
};
const postTo = (suffix: string) => (r: Request) => r.method() === "POST" && new URL(r.url()).pathname + new URL(r.url()).search === suffix;
const NEW_FUNCTION = "궤도 틀림의 진행을 미리 알아낸다";

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: "ignoreErrors" });
});

test("네 칸 → 카드 4줄 → 기능 문장 고치기 → 과제안·보강 질문·초안 요청에 고친 카드가 실린다", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await login(page);
  const stub = await stubProblemCard(page);
  await fillIdea(page);

  // 입력이 멈추면 뒤에서 진단 — 카드 4줄
  const card = problemCard(page);
  await expect(card).toBeVisible();
  expect(stub.diagnoses).toHaveLength(1);
  expect(stub.diagnoses[0]).toMatchObject({ current_state: "궤도 틀림이 반복 발생함", goal: "검측 이력 기반 보수 우선순위 산정" });
  expect(stub.diagnoses[0]).not.toHaveProperty("previous");
  await expect(card.getByRole("heading", { name: "핵심 문제" })).toBeVisible();
  for (const key of ["function", "cause", "contradiction", "codes"]) await expect(card.getByTestId(`card-line-${key}`).getByTestId("card-line-text")).not.toBeEmpty();
  if (!REAL_CARD) {
    await expect(card.getByTestId("card-line-function")).toContainText("궤도 틀림의 진행을 늦춘다");
    await expect(card.getByTestId("card-line-function").getByTestId("card-basis")).toHaveText("근거 있음");
    await expect(card.getByTestId("card-line-cause").getByTestId("card-needs-check")).toHaveText("확인 필요");
    await expect(card.getByTestId("card-line-contradiction").getByTestId("card-basis")).toHaveText("추정");
    await expect(card.getByTestId("card-code-unverified")).toHaveText("확인 못 함");
  }

  // 전문가 분석은 접혀 있다 — 펼치면 항목 나누기·사다리·영문 기능 문장·발명 원리
  const expert = card.getByTestId("problem-card-expert");
  await expect(expert.getByTestId("card-ladder")).toBeHidden();
  await expert.getByText("전문가 분석 펼치기").click();
  await expect(expert.getByTestId("card-facets")).toBeVisible();
  await expect(expert.getByTestId("card-ladder").getByRole("listitem")).toHaveCount(3);
  await expect(expert.getByTestId("card-function-en")).toBeVisible();
  await expect(expert.getByTestId("card-principles")).toBeVisible();
  await expectNoInternalIds(page);
  await expectNoRunWord(page);
  await shot(page, "01-idea-card");

  // 기능 문장만 고친다 → 수정 요청 본문(네 칸·before·after·fields) → 응답 카드로 갈아 끼움
  await card.getByRole("button", { name: "기능 문장 고치기" }).click();
  await shot(page, "02-edit-line");
  await card.getByRole("textbox", { name: "기능 문장", exact: true }).fill(NEW_FUNCTION);
  await card.getByRole("button", { name: "적용" }).click();
  await expect(card.getByTestId("card-line-function").getByTestId("card-line-text")).toContainText(REAL_CARD ? /.+/ : NEW_FUNCTION);
  await expect(card.getByTestId("card-line-function").getByTestId("card-by-user")).toHaveText("직접 고침");
  expect(stub.edits).toHaveLength(1);
  const edit = stub.edits[0] as { request: Record<string, string>; before: any; after: any; fields: string[] }; // eslint-disable-line @typescript-eslint/no-explicit-any
  expect(edit.fields).toEqual(["function_ko"]);
  expect(edit.request.root_cause).toBe("다짐 효과가 오래 가지 않음");
  expect(edit.after.function_ko.value).toBe(NEW_FUNCTION);
  expect(edit.before.function_ko.value).not.toBe(NEW_FUNCTION);
  // 고친 뒤 같은 네 칸으로 다시 진단하지 않는다
  expect(stub.diagnoses).toHaveLength(1);

  // [다음] — 유사과제 확인 요청에는 카드가 없고, 뒤따르는 과제안 요청에 고친 카드가 실린다
  const precheckReq = page.waitForRequest(postTo("/v1/precheck?stage=rule"));
  const planReq = page.waitForRequest(postTo("/v1/precheck/recommendations"));
  await goPrecheck(page, page.getByRole("button", { name: "다음: 유사과제 확인" }));
  expect((await precheckReq).postDataJSON()).not.toHaveProperty("problem_card");
  const plan = (await planReq).postDataJSON() as { problem_card?: any }; // eslint-disable-line @typescript-eslint/no-explicit-any
  expect(plan.problem_card?.function_ko).toMatchObject({ origin: "user" });
  if (!REAL_CARD) expect(plan.problem_card.function_ko.value).toBe(NEW_FUNCTION);
  // 서버가 카드가 실린 요청을 받아 과제안을 만든다
  await expect(page.getByTestId("plan-card").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("plans-stale-note")).toHaveCount(0);
  // ①·② 에서 콘솔 오류 없음 (초안 화면의 기존 조회 404 는 이 시험 범위 밖이라 여기서 본다)
  expect(errors).toEqual([]);

  // ③ 보강 질문·초안 생성 요청에도 같은 카드
  await page.getByRole("button", { name: /다음: 선행연구 브리핑/ }).click();
  await expect(page).toHaveURL(/\/new\/brief$/);
  const clarifyReq = page.waitForRequest(postTo("/v1/precheck/clarify"));
  await page.getByRole("button", { name: /다음: 보강 질문/ }).click();
  await expect(page).toHaveURL(/\/new\/clarify$/);
  expect(((await clarifyReq).postDataJSON() as { problem_card?: any }).problem_card?.function_ko.origin).toBe("user"); // eslint-disable-line @typescript-eslint/no-explicit-any
  const createReq = page.waitForRequest(postTo("/v1/runs"));
  await page.getByRole("button", { name: /초안 생성 시작|답하고 생성 시작/ }).click();
  // 생성 요청은 입력 칸이 몸통에 그대로 놓인다(RunIn)
  const created = (await createReq).postDataJSON() as { problem_card?: any }; // eslint-disable-line @typescript-eslint/no-explicit-any
  expect(created.problem_card?.function_ko.origin).toBe("user");
  await expect(page).toHaveURL(/\/runs\/[0-9a-f-]+(\/draft)?$/, { timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "초안 본문" })).toBeVisible({ timeout: 30_000 });
});

test("진단이 느리면 [다음] 은 기다리지 않고 카드 없이 진행한다", async ({ page }) => {
  test.skip(REAL_CARD, "가로챈 응답으로만 — 실제 서버의 진단은 붙잡아 둘 수 없다");
  await login(page);
  const stub = await stubProblemCard(page, { hold: true });
  await fillIdea(page);
  // 카드 자리에 작은 한 줄만 — 입력·다음 버튼은 그대로 쓸 수 있다
  await expect(page.getByTestId("problem-card-pending")).toHaveText("문제 정리 중…");
  await expect(problemCard(page)).toHaveCount(0);
  await expect(page.getByLabel(/해결 목표/)).toBeEnabled();

  const planReq = page.waitForRequest(postTo("/v1/precheck/recommendations"));
  await goPrecheck(page, page.getByRole("button", { name: "다음: 유사과제 확인" }));
  expect((await planReq).postDataJSON()).not.toHaveProperty("problem_card");
  await expect(page.getByTestId("plan-card").first()).toBeVisible({ timeout: 30_000 });
  expect(stub.diagnoses).toHaveLength(1);
  stub.release();
  // 늦게 온 진단은 버린다 — 들고 다니는 입력에 카드가 없다
  const stored = await page.evaluate(() => JSON.parse(sessionStorage.getItem("rra-idea") ?? "{}") as { request?: Record<string, unknown>; problemCard?: unknown });
  expect(stored.request).not.toHaveProperty("problem_card");
  expect(stored.problemCard ?? null).toBeNull();
});

for (const [name, diagnose] of [
  ["꺼짐(status off)", DIAGNOSE_OFF],
  ["서버 오류(500)", 500],
  ["경로 없음(404)", 404],
] as const) {
  test(`진단이 ${name} 이면 카드 영역이 없다 — 종전 화면 그대로 다음으로`, async ({ page }) => {
    test.skip(REAL_CARD, "가로챈 응답으로만");
    await login(page);
    const stub = await stubProblemCard(page, { diagnose });
    await fillIdea(page);
    await expect.poll(() => stub.diagnoses.length, { timeout: 10_000 }).toBe(1);
    await page.waitForTimeout(500);
    await expect(problemCard(page)).toHaveCount(0);
    await expect(page.getByTestId("problem-card-pending")).toHaveCount(0);
    await expect(page.getByText("핵심 문제")).toHaveCount(0);
    await expect(page.getByRole("alert")).toHaveCount(0);
    const planReq = page.waitForRequest(postTo("/v1/precheck/recommendations"));
    await goPrecheck(page, page.getByRole("button", { name: "다음: 유사과제 확인" }));
    expect((await planReq).postDataJSON()).not.toHaveProperty("problem_card");
    // 같은 입력으로 다시 부르지 않는다
    expect(stub.diagnoses).toHaveLength(1);
  });
}

test("과제안을 받은 뒤 카드를 고치면 ② 에 '문제 정의가 바뀌었습니다' + [과제안 다시 만들기] — 자동으로 다시 만들지 않는다", async ({ page }) => {
  await login(page);
  const stub = await stubProblemCard(page);
  let plans = 0;
  page.on("request", (r) => {
    if (postTo("/v1/precheck/recommendations")(r)) plans += 1;
  });
  await fillIdea(page);
  await expect(problemCard(page)).toBeVisible();
  await goPrecheck(page, page.getByRole("button", { name: "다음: 유사과제 확인" }));
  await expect(page.getByTestId("plan-card").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("plans-stale-note")).toHaveCount(0);
  expect(plans).toBe(1);

  // ① 로 돌아가 모순을 고친다 (모순 수정도 자동 실행 없음)
  await page.getByRole("button", { name: /이전 단계: 아이디어 입력/ }).click();
  await expect(page).toHaveURL(/\/new$/);
  const card = problemCard(page);
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "모순 고치기" }).click();
  await card.getByLabel("좋게 하려는 것").fill("검측 주기 단축");
  await card.getByLabel("그 때문에 나빠지는 것").fill("검측 비용 증가");
  await card.getByRole("button", { name: "적용" }).click();
  await expect(card.getByTestId("card-line-contradiction").getByTestId("card-by-user")).toBeVisible();
  expect((stub.edits[0] as { fields: string[] }).fields).toEqual(["contradiction"]);
  // 돌아와서 다시 진단하지 않았다(같은 네 칸)
  expect(stub.diagnoses).toHaveLength(1);

  // ② 로 되돌아가면 한 줄과 버튼 — 기다려도 과제안 요청은 늘지 않는다
  await page.goBack();
  await expect(page).toHaveURL(/\/new\/precheck$/);
  const note = page.getByTestId("plans-stale-note");
  await expect(note).toContainText("문제 정의가 바뀌었습니다.");
  await page.waitForTimeout(1500);
  expect(plans).toBe(1);
  await expectNoInternalIds(page);
  await expectNoRunWord(page);
  await shot(page, "03-precheck-plans-stale");

  const again = page.waitForRequest(postTo("/v1/precheck/recommendations"));
  await note.getByRole("button", { name: "과제안 다시 만들기" }).click();
  const sent = (await again).postDataJSON() as { problem_card?: any }; // eslint-disable-line @typescript-eslint/no-explicit-any
  expect(sent.problem_card?.contradiction.origin).toBe("user");
  if (!REAL_CARD) expect(sent.problem_card.contradiction.improve).toBe("검측 주기 단축");
  await expect(note).toHaveCount(0);
  await expect(page.getByTestId("plan-card").first()).toBeVisible({ timeout: 30_000 });
  expect(plans).toBe(2);
});
