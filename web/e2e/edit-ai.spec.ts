import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fillIdea, login, subnav, goPrecheck } from "./helpers";

/** RRA_SCREENS_DIR 가 있으면 화면을 캡처한다 (docs/history/screens/2026-10-28-edit-ai-NN-*.png) */
const OUT = process.env.RRA_SCREENS_DIR ?? "";
async function shot(page: Page, n: number, name: string) {
  if (!OUT) return;
  fs.mkdirSync(OUT, { recursive: true });
  await page.screenshot({ path: path.join(OUT, `2026-10-28-edit-ai-${String(n).padStart(2, "0")}-${name}.png`), fullPage: true });
}

// 작성·편집 AI (레인 B, 2026-10-28) — 가짜 모드: 보강 질문의 정책적 중요도 작성안 고르기 → 생성 →
// 2-가-(1) 이 고른 안 그대로 → ④ AI 다시 쓰기(Argon)·보완 질문(Argon) → 변경 없이 저장 → 팝업 → 최종 검토
test("보강 질문 정책 작성안 → 생성 → AI 다시 쓰기·보완 질문 → 변경 없이 저장 팝업", async ({ page }) => {
  await login(page);
  await fillIdea(page, " (정책 작성안)");
  await goPrecheck(page);
  await page.getByRole("button", { name: /다음: 선행연구 브리핑|원래 아이디어로 진행/ }).first().click();
  if (page.url().endsWith("/new/precheck")) await page.getByRole("button", { name: /다음: 선행연구 브리핑/ }).click();
  await page.getByRole("button", { name: /다음: 보강 질문/ }).click();
  await expect(page).toHaveURL(/\/new\/clarify$/);

  // ③ 보강 질문 — Argon 질문 + 정책 근거 질문 자리에 작성안 (방향별, 근거 겹침 없음)
  await expect(page.getByText(/질문 \d개/)).toBeVisible();
  await expect(page.getByText("Argon 이 물음")).toBeVisible();
  const list = page.getByRole("list", { name: "정책적 중요도 작성안 목록" });
  await expect(list.getByText("정부 계획", { exact: true })).toBeVisible();
  await expect(list.getByText("공사 전략", { exact: true })).toBeVisible();
  await expect(list.getByText("감사 지적·현안", { exact: true })).toBeVisible();
  await expect(list.getByRole("link", { name: /원문 보기/ }).first()).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 900 });
  await shot(page, 1, "clarify-policy-cards");
  await page.getByRole("button", { name: "이 안으로 — 공사 전략" }).click();
  await expect(page.getByText("고른 정책 근거: 작성안 그대로")).toBeVisible();
  await page.getByLabel(/적용할 노선·구간/).fill("경부선 대전~대구");
  await page.getByRole("button", { name: "답하고 생성 시작" }).click();
  await expect(page.getByRole("heading", { name: "초안 본문" })).toBeVisible({ timeout: 30_000 });
  const id = /\/runs\/([0-9a-f-]+)/.exec(page.url())![1]!;

  // 2-가-(1) 은 고른 안 그대로
  await expect(page.getByText("인용 자료가 제시한 방향과 본 제안의 해결 목표가 이어짐.").first()).toBeVisible();

  // ④ AI 다시 쓰기 (Argon) — 새 후보가 있고 반영할 수 있다
  await subnav(page, "직접 수정").click();
  await expect(page).toHaveURL(new RegExp(`/runs/${id}/edit$`));
  await expect(page.getByText(/변경 0건/)).toBeVisible();
  await page.getByRole("button", { name: "2-다 연구 방법 및 주요내용 AI 다시 쓰기" }).click();
  const rw = page.getByRole("dialog", { name: /AI 다시 쓰기 — 2-다/ });
  await expect(rw.getByText(/Argon 이 같은 지시·근거로 다시 씁니다/)).toBeVisible();
  await expect(rw.getByText(/새 후보 \d+문장/)).toBeVisible();
  await shot(page, 2, "rewrite-argon");
  await rw.getByRole("button", { name: "닫기", exact: true }).last().click();

  // 보완 질문 (Argon) → [답 반영해 다시 쓰기]
  await page.getByRole("button", { name: "2-가-(2) 기술적 중요도 보완 질문" }).click();
  const qd = page.getByRole("dialog", { name: /보완 질문 — 2-가-\(2\)/ });
  await expect(qd.getByText("Argon 이 본문을 읽고 물음")).toBeVisible();
  await expect(qd.getByText("[국외 동향]")).toBeVisible();
  await qd.getByLabel(/국외 선행연구는/).fill("독일 DB 가 예측 정비를 도입함");
  await shot(page, 3, "section-questions-argon");
  await qd.getByRole("button", { name: /답 반영해 다시 쓰기/ }).click();
  const rw2 = page.getByRole("dialog", { name: /AI 다시 쓰기 — 2-가-\(2\)/ });
  await expect(rw2.getByText(/새 후보 \d+문장/)).toBeVisible();
  await rw2.getByRole("button", { name: "닫기", exact: true }).last().click();
  await expect(page.getByText(/변경 1건/)).toBeVisible(); // 보완 메모

  // 저장하지 않은 편집이 없어도 버튼은 켜져 있다 → 팝업 → [확인] 은 최종 검토로
  const save = page.getByRole("button", { name: "새 버전으로 저장" });
  await expect(save).toBeEnabled();
  await save.click();
  const ask = page.getByRole("dialog", { name: "저장했습니다" });
  await expect(ask.getByText(/이미 v\d+ 까지 저장되어 있습니다. 최종 검토로 넘어갈까요?/)).toBeVisible();
  await shot(page, 4, "save-ask");
  await ask.getByRole("button", { name: "확인" }).click();
  await expect(page).toHaveURL(new RegExp(`/runs/${id}/final-review$`));
});

test("변경이 없으면 '변경된 내용이 없습니다' — [취소] 는 그대로", async ({ page }) => {
  await login(page);
  await fillIdea(page, " (변경 없음)");
  await goPrecheck(page);
  await page.getByRole("button", { name: /다음: 선행연구 브리핑|원래 아이디어로 진행/ }).first().click();
  await page.getByRole("button", { name: /다음: 보강 질문/ }).click();
  await page.getByRole("button", { name: "건너뛰고 생성" }).click();
  await expect(page.getByRole("heading", { name: "초안 본문" })).toBeVisible({ timeout: 30_000 });
  const id = /\/runs\/([0-9a-f-]+)/.exec(page.url())![1]!;
  await subnav(page, "직접 수정").click();
  await page.getByRole("button", { name: "새 버전으로 저장" }).click();
  const ask = page.getByRole("dialog", { name: "변경된 내용이 없습니다" });
  await expect(ask.getByText("변경된 내용이 없습니다. 최종 검토로 넘어갈까요?")).toBeVisible();
  await ask.getByRole("button", { name: "취소" }).click();
  await expect(page).toHaveURL(new RegExp(`/runs/${id}/edit$`));
  // 2-가-(1) 이 비었으면 [정책 근거 넣기·바꾸기] — 같은 작성안에서 골라 새 버전 (ADR 0052)
  await page.getByRole("button", { name: "정책 근거 넣기·바꾸기" }).click();
  const pd = page.getByRole("dialog", { name: /정책 근거 넣기·바꾸기/ });
  await pd.getByRole("button", { name: "이 안으로 — 정부 계획" }).click();
  await expect(page.getByText(/정책 근거를 v\d+ 으로 반영했습니다/).first()).toBeVisible();
  await expect(page.getByText(/변경 [1-9]\d*건/)).toBeVisible();
});
