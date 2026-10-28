/** [G] 그림 카드 — 가짜 백엔드(RRA_FAKE_LLM)는 run 마다 v2 기본 그림 3장(As-Is/To-Be/objective ·
 *  추천 SWOT/tech_importance · 추천 비용-편익/expected_management, 전부 "Nano Banana Pro")을 돌려준다.
 *  글자 고치기 → 확인함 → 빼기 → 버전 비교 → v1 복원 → 최종 검토 → 최종 마무리 확인 대화상자,
 *  추천 그림 넣기 확정·필요 없음(접힘)·다시 넣기·다른 기법으로 바꾸기. */
import { expect, test } from "@playwright/test";
import { createRun, login, subnav } from "./helpers";

test.describe("[G] 그림 카드", () => {
  test("글자 고치기 → 확인함 → 빼기 → 버전 비교(그림 변경) → v1 복원 → 최종 마무리 확인 대화상자", async ({ page }) => {
    await login(page);
    const id = await createRun(page);

    // ③ 초안 보기: 읽기 전용 카드 (확인함만)
    await expect(page.getByRole("group", { name: "현재·연구 후 비교 그림" })).toBeVisible();
    await expect(page.getByRole("button", { name: "현재·연구 후 비교 그림 글자 고치기" })).toHaveCount(0);

    // ④ 직접 수정: 카드 + 배지 "확인 전"
    await subnav(page, "직접 수정").click();
    await expect(page).toHaveURL(new RegExp(`/runs/${id}/edit$`));
    const card = page.getByRole("group", { name: "현재·연구 후 비교 그림" });
    await expect(card).toBeVisible();
    await expect(card.getByText("확인 전", { exact: true })).toBeVisible();
    await expect(card.getByText("Nano Banana Pro")).toBeVisible();
    await expect(card.getByText(/AI 가 그린 그림입니다/)).toBeVisible();
    // [23] 그림은 가로로 넓게 — 카드 이미지는 폭이 높이보다 크고, 본문 폭 안내가 붙는다
    const img = card.getByTestId("figure-image");
    await expect(img).toBeVisible();
    const box = await img.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeGreaterThan(box!.height * 1.5);
    await expect(card.getByText(/본문 폭 \d+(\.\d+)?mm/)).toBeVisible();
    await expect(card.getByText("현재·연구 후 비교 그림", { exact: true })).toHaveCount(0);
    // v2: 개념도·체계도·로드맵은 자동으로 넣지 않는다 — 추천 기법 그림 2장
    await expect(page.getByRole("group", { name: "분석 기법 그림 – SWOT 분석" })).toBeVisible();
    await expect(page.getByRole("group", { name: "분석 기법 그림 – 비용-편익 분석" })).toBeVisible();
    await expect(page.getByRole("group", { name: "연구 개념도" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "다른 그림 추가" })).toBeEnabled();

    // 글자 고치기 → 첫 칸 바꿈 → 적용 → 새 버전 toast, 카드 유지
    await card.getByRole("button", { name: "현재·연구 후 비교 그림 글자 고치기" }).click();
    const textsDialog = page.getByRole("dialog");
    await expect(textsDialog).toBeVisible();
    const firstInput = textsDialog.getByRole("textbox").first();
    await firstInput.fill("고친 글자");
    await textsDialog.getByRole("button", { name: /적용/ }).click();
    await expect(page.getByText(/으로 저장했습니다/).first()).toBeVisible();
    await expect(textsDialog).toBeHidden();
    await expect(page.getByRole("group", { name: "현재·연구 후 비교 그림" })).toBeVisible();

    // 확인함 → 배지 "확인함"(버튼은 사라진다)
    await page.getByRole("group", { name: "현재·연구 후 비교 그림" }).getByRole("button", { name: "현재·연구 후 비교 그림 확인함" }).click();
    await expect(page.getByText("확인 표시를 저장했습니다 (새 버전 없음)").first()).toBeVisible(); // 항목 21
    await expect(page.getByRole("group", { name: "현재·연구 후 비교 그림" }).getByText("확인함", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "현재·연구 후 비교 그림 확인함" })).toHaveCount(0);

    // 빼기 → 배지 "뺌", 버튼은 [넣기]
    await page.getByRole("group", { name: "현재·연구 후 비교 그림" }).getByRole("button", { name: "현재·연구 후 비교 그림 빼기" }).click();
    await expect(page.getByRole("group", { name: "현재·연구 후 비교 그림" }).getByText("뺌", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "현재·연구 후 비교 그림 넣기" })).toBeVisible();

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

  test("[다른 그림 추가] 대화상자: 종류 8개·기본 섹션", async ({ page }) => {
    await login(page);
    await createRun(page);
    await subnav(page, "직접 수정").click();
    await page.getByRole("button", { name: "다른 그림 추가" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("radio")).toHaveCount(8);
    await expect(dialog.getByLabel("넣을 섹션")).toHaveValue("objective");
    // 일정표는 연구기간이 없는 가짜 입력에서 만들 수 없다 → 체계도를 하나 더 추가
    await dialog.getByText("추진 체계도", { exact: true }).click();
    await expect(dialog.getByLabel("넣을 섹션")).toHaveValue("method");
    await dialog.getByRole("button", { name: "추가", exact: true }).click();
    await expect(page.getByText(/으로 저장했습니다/).first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("group", { name: "추진 체계도" })).toHaveCount(1);
  });

  test("그림 추천 넣기·빼기 — 넣기 확정, 필요 없음(접힘)·다시 넣기, 다른 기법으로 바꾸기", async ({ page }) => {
    await login(page);
    await createRun(page);
    await subnav(page, "직접 수정").click();
    await expect(page.getByText("분석 기법 추천: 추천함")).toBeVisible();
    const swot = page.getByRole("region", { name: "추천 — SWOT 분석" });
    await expect(swot.getByText("결정 전")).toBeVisible();
    await expect(page.getByText(/제안 내용 기반 예비 평가/).first()).toBeVisible();

    // 넣기 확정 → 상태 표시(새 버전 없음, 항목 21), 배지 "넣기 확정"
    await page.getByRole("button", { name: "분석 기법 그림 – SWOT 분석 넣기 확정" }).click();
    await expect(page.getByText("확인 표시를 저장했습니다 (새 버전 없음)").first()).toBeVisible();
    await expect(page.getByRole("region", { name: "추천 — SWOT 분석" }).getByText("넣기 확정", { exact: true })).toBeVisible();

    // 필요 없음 → 카드가 섹션 아래로 접힌다 → 다시 넣기
    await page.getByRole("button", { name: "분석 기법 그림 – 비용-편익 분석 필요 없음" }).click();
    await expect(page.getByRole("group", { name: "분석 기법 그림 – 비용-편익 분석" })).toHaveCount(0);
    await page.getByText("필요 없다고 한 추천 그림 1장").click();
    await page.getByRole("button", { name: "분석 기법 그림 – 비용-편익 분석 다시 넣기" }).click();
    await expect(page.getByRole("group", { name: "분석 기법 그림 – 비용-편익 분석" })).toBeVisible();

    // 다른 기법으로 바꾸기 → 퓨 매트릭스로 다시 분석 (같은 자리, 결정 전)
    await page.getByRole("button", { name: "분석 기법 그림 – SWOT 분석 다른 기법으로 바꾸기" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("radio", { name: /퓨 매트릭스/ }).check();
    await dialog.getByRole("button", { name: "바꾸기" }).click();
    await expect(page.getByRole("group", { name: "분석 기법 그림 – 퓨 매트릭스" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("region", { name: "추천 — 퓨 매트릭스" }).getByText("결정 전")).toBeVisible();

    // 버전·비교: 추천 결정도 그림 변경으로 센다
    await subnav(page, "버전·비교").click();
    await expect(page.getByText("그림 변경").first()).toBeVisible();
  });
});
