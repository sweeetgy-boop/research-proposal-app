/** [G] 그림 카드 — 가짜 백엔드(RRA_FAKE_LLM)는 run 마다 그림 3장(concept/objective · process/method ·
 *  roadmap/expected_technology, 전부 "Nano Banana Pro")을 돌려준다. 글자 고치기 → 확인함 → 빼기 → 버전 비교 →
 *  v1 복원(확인 전으로 되돌아감) → 최종 검토 → 최종 마무리에서 확인 전 그림 알림·확인 대화상자. */
import { expect, test } from "@playwright/test";
import { createRun, login, subnav } from "./helpers";

test.describe("[G] 그림 카드", () => {
  test("글자 고치기 → 확인함 → 빼기 → 버전 비교(그림 변경) → v1 복원 → 최종 마무리 확인 대화상자", async ({ page }) => {
    await login(page);
    const id = await createRun(page);

    // ③ 초안 보기: 읽기 전용 카드 (확인함만)
    await expect(page.getByRole("group", { name: "연구 개념도" })).toBeVisible();
    await expect(page.getByRole("button", { name: "연구 개념도 글자 고치기" })).toHaveCount(0);

    // ④ 직접 수정: 카드 + 배지 "확인 전"
    await subnav(page, "직접 수정").click();
    await expect(page).toHaveURL(new RegExp(`/runs/${id}/edit$`));
    const card = page.getByRole("group", { name: "연구 개념도" });
    await expect(card).toBeVisible();
    await expect(card.getByText("확인 전", { exact: true })).toBeVisible();
    await expect(card.getByText("Nano Banana Pro")).toBeVisible();
    await expect(card.getByText(/AI 가 그린 그림입니다/)).toBeVisible();
    await expect(page.getByRole("group", { name: "추진 체계도" })).toBeVisible();
    await expect(page.getByRole("group", { name: "성과지표·활용 로드맵" })).toBeVisible();
    await expect(page.getByRole("button", { name: "다른 그림 추가" })).toBeEnabled();

    // 글자 고치기 → 첫 칸 바꿈 → 적용 → 새 버전 toast, 카드 유지
    await card.getByRole("button", { name: "연구 개념도 글자 고치기" }).click();
    const textsDialog = page.getByRole("dialog");
    await expect(textsDialog).toBeVisible();
    const firstInput = textsDialog.getByRole("textbox").first();
    await firstInput.fill("고친 글자");
    await textsDialog.getByRole("button", { name: /적용/ }).click();
    await expect(page.getByText(/으로 저장했습니다/).first()).toBeVisible();
    await expect(textsDialog).toBeHidden();
    await expect(page.getByRole("group", { name: "연구 개념도" })).toBeVisible();

    // 확인함 → 배지 "확인함"(버튼은 사라진다)
    await page.getByRole("group", { name: "연구 개념도" }).getByRole("button", { name: "연구 개념도 확인함" }).click();
    await expect(page.getByText(/으로 저장했습니다/).first()).toBeVisible();
    await expect(page.getByRole("group", { name: "연구 개념도" }).getByText("확인함", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "연구 개념도 확인함" })).toHaveCount(0);

    // 빼기 → 배지 "뺌", 버튼은 [넣기]
    await page.getByRole("group", { name: "연구 개념도" }).getByRole("button", { name: "연구 개념도 빼기" }).click();
    await expect(page.getByRole("group", { name: "연구 개념도" }).getByText("뺌", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "연구 개념도 넣기" })).toBeVisible();

    // 버전·비교: 마지막 두 버전 비교에 "그림 변경"
    await subnav(page, "버전·비교").click();
    await expect(page.getByRole("heading", { name: /버전 \d+개/ })).toBeVisible();
    await expect(page.getByText("그림 변경").first()).toBeVisible();
    await expect(page.getByText(/그림 \d+/).first()).toBeVisible();

    // v1 복원 (확인창) → 그림도 v1 상태(확인 전)로
    await page.getByRole("button", { name: /v1 으로 복원/ }).click();
    const restoreDialog = page.getByRole("dialog");
    await expect(restoreDialog).toBeVisible();
    await restoreDialog.getByRole("button", { name: "복원", exact: true }).click();
    await expect(page.getByText(/v1 내용으로 v\d+ 을 만들었습니다/).first()).toBeVisible();

    // ⑤ 최종 검토 (마무리 조건)
    await subnav(page, "최종 검토").click();
    await page.getByRole("button", { name: "최종 검토 요청" }).click();
    await expect(page.getByRole("heading", { name: /Argon 최종 검토/ })).toBeVisible({ timeout: 30_000 });

    // ⑥ 최종 마무리: 확인 전 그림 알림 + 마무리 전 확인 대화상자 → 취소
    await subnav(page, "최종 마무리").click();
    await expect(page.getByText(/확인 전 그림 \d+개/).first()).toBeVisible();
    await page.getByRole("button", { name: "HWPX 내려받기" }).click();
    const askDialog = page.getByRole("dialog");
    await expect(askDialog).toBeVisible();
    await expect(askDialog.getByText(/그림을 확인하지 않았습니다/)).toBeVisible();
    await askDialog.getByRole("button", { name: "취소" }).click();
    await expect(askDialog).toBeHidden();
    await expect(page.getByText("마무리됨")).toHaveCount(0);
  });

  test("[다른 그림 추가] 대화상자: 종류 6개·기본 섹션", async ({ page }) => {
    await login(page);
    await createRun(page);
    await subnav(page, "직접 수정").click();
    await page.getByRole("button", { name: "다른 그림 추가" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("radio")).toHaveCount(6);
    await expect(dialog.getByLabel("넣을 섹션")).toHaveValue("objective");
    // 일정표는 연구기간이 없는 가짜 입력에서 만들 수 없다 → 체계도를 하나 더 추가
    await dialog.getByText("추진 체계도", { exact: true }).click();
    await expect(dialog.getByLabel("넣을 섹션")).toHaveValue("method");
    await dialog.getByRole("button", { name: "추가", exact: true }).click();
    await expect(page.getByText(/으로 저장했습니다/).first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("group", { name: "추진 체계도" })).toHaveCount(2);
  });
});
