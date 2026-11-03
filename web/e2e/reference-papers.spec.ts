import { expect, test } from "@playwright/test";
import { fillIdea, login, goPrecheck } from "./helpers";
import { expectNoInternalIds } from "./helpers-text";

// ② 참고 논문 (ADR 0053, 가짜 모드). 아이디어 끝의 " (추천 없음)" 표식이면 가짜 추천기가 0건을 낸다
// ('새 영역' 1회 재요청 뒤에도 0건). 참고 논문(scienceon:fake-1 — "궤도 틀림 진행 속도 추정 논문 (가짜)")을 고르면 카드가 나온다.
const PAPER = "궤도 틀림 진행 속도 추정 논문 (가짜)";

test("관련 연구 1건 체크 → [선택 적용] → 비교표 '선행연구' 열 → 과제안 카드 ≥1", async ({ page }) => {
  await login(page);
  await fillIdea(page, " (추천 없음)");
  await goPrecheck(page);

  // 처음에는 유사함 0·참고 0 → 과제안 0건 + 참고 논문 안내
  await expect(page.getByTestId("plan-reference-hint")).toBeVisible();
  await expect(page.getByTestId("plan-card")).toHaveCount(0);

  const section = page.getByRole("region", { name: /관련 연구 \d+건/ });
  const box = section.getByRole("checkbox", { name: new RegExp(`^차별화에 참고 — ${PAPER.replace(/[()]/g, "\\$&")}`) });
  await expect(box).not.toBeChecked();
  await box.check();
  await expect(section.getByTestId("reference-limit-note")).toHaveText("참고로 고른 자료 1건 (최대 5건)");

  const bar = page.getByTestId("precheck-summary-bar");
  await expect(bar.getByText(/선택이 바뀌었습니다/)).toBeVisible();
  await bar.getByRole("button", { name: "선택 적용" }).click();

  // 비교표에 '선행연구' 열 — 유사함 0건이어도 비지 않는다
  const compare = page.getByRole("table", { name: /차별성 비교표/ });
  await expect(compare).toBeVisible();
  await expect(compare.getByTestId("comparison-kind").filter({ hasText: "선행연구" }).first()).toBeVisible();
  await expect(compare.getByText(PAPER).first()).toBeVisible();

  // [선택 적용] 은 참고 논문이 바뀌면 과제안도 다시 받는다 — 고른 논문을 근거로 카드 ≥1, 0건 안내는 사라진다
  const cards = page.getByTestId("plan-card");
  await expect(cards.first()).toBeVisible();
  expect(await cards.count()).toBeGreaterThanOrEqual(1);
  await expect(cards.first().getByText(PAPER)).toBeVisible(); // 근거 과제·자료에 참고 논문
  await expect(page.getByTestId("plan-reference-hint")).toHaveCount(0);

  await expectNoInternalIds(page);
});

test("유사함 0·참고 0 → 과제안 0건 안내 문구와 [원래 아이디어로 진행]", async ({ page }) => {
  await login(page);
  await fillIdea(page, " (추천 없음)");
  await goPrecheck(page);

  const hint = page.getByTestId("plan-reference-hint");
  await expect(hint).toBeVisible();
  await expect(hint).toContainText("관련 연구에서 참고 논문을 골라 [과제안 다시 만들기]");
  await expect(page.getByTestId("plan-retry-note")).toBeVisible(); // '새 영역' 기준으로 한 번 더 받음
  const actions = page.getByTestId("plan-empty-actions");
  await expect(actions.getByRole("button", { name: "과제안 다시 만들기" })).toBeVisible();
  await expect(actions.getByRole("button", { name: "원래 아이디어로 진행" })).toBeVisible();
  // 고른 참고 논문이 없으면 0건 안내의 [과제안 다시 만들기] 는 꺼져 있다
  const regen = actions.getByRole("button", { name: "과제안 다시 만들기" });
  await expect(regen).toBeDisabled();
  await expectNoInternalIds(page);

  // 논문을 고르면([선택 적용] 없이도) 0건 안내의 [과제안 다시 만들기] 로 그 논문을 근거로 다시 받는다
  const section = page.getByRole("region", { name: /관련 연구 \d+건/ });
  await section.getByTestId("reference-checkbox").first().check();
  await expect(regen).toBeEnabled();
  await regen.click();
  await expect(page.getByTestId("plan-card").first()).toBeVisible();
  await expect(hint).toHaveCount(0);
});
