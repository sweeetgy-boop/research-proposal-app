import { expect, test } from "@playwright/test";
import { createRun, detailMode, fillIdea, login, subnav } from "./helpers";

test.describe("전체 흐름 ①→⑥", () => {
  test("아이디어 → 유사과제(추천 0건) → 보강 질문 없음 → 생성 → 초안 → 수정 → 버전 비교 → 최종 검토 → HWPX 내려받기 → 다시 열기", async ({ page }) => {
    await login(page);

    // ① 입력 검증: 빈 제출 (상세 입력)
    await detailMode(page);
    await page.getByRole("button", { name: "유사과제 확인" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "필수 슬롯이 비었습니다" })).toBeVisible();

    // ①→②→③
    const id = await createRun(page);
    await expect(page.getByRole("heading", { name: "2-다 연구 방법 및 주요내용" })).toBeVisible();
    await expect(page.getByText("Argon 보완").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Argon 1차 검토" })).toBeVisible();

    // ④ 직접 수정: 수정안 사용은 1차 검토에서 이미 반영되어 없음 → 직접 수정 + 메모 + 저장
    await subnav(page, "직접 수정").click();
    await expect(page).toHaveURL(new RegExp(`/runs/${id}/edit$`));
    const group = page.getByRole("radiogroup", { name: "2-나 연구목적 문장 1 처리" });
    await group.getByText("직접 수정", { exact: true }).click();
    const ta = page.getByRole("textbox", { name: /2-나 연구목적 문장 1 직접 수정|문장 1 직접 수정/ }).first();
    await ta.fill("궤도 틀림 진행 속도를 추정해 보수 우선순위를 산정하고 현장에 적용함.");
    await expect(page.getByText(/임시 저장됨/)).toBeVisible({ timeout: 10_000 }); // autosave → 서버
    await page.getByLabel(/저장 메모/).fill("목적 문장 보강");
    await page.getByRole("button", { name: "새 버전으로 저장" }).click();
    await expect(page).toHaveURL(new RegExp(`/runs/${id}/draft$`));
    await expect(page.getByText(/v3 으로 저장했습니다/).first()).toBeVisible();

    // 버전·비교
    await subnav(page, "버전·비교").click();
    await expect(page.getByRole("heading", { name: /버전 3개/ })).toBeVisible();
    await expect(page.locator("ins.diff-ins").first()).toBeVisible();

    // ⑤ 최종 검토
    await subnav(page, "최종 검토").click();
    await page.getByRole("button", { name: "최종 검토 요청" }).click();
    await expect(page.getByRole("heading", { name: /Argon 최종 검토/ })).toBeVisible({ timeout: 30_000 });

    // ⑥ 최종 마무리: 선택형·제안자 정보 → 파일
    await subnav(page, "최종 마무리").click();
    await expect(page.getByRole("radio", { name: "응용연구" })).toBeChecked();
    await page.getByLabel("제안부서").fill("철도연구원");
    await page.getByLabel("제안자 성명").fill("홍길동");
    // [G] 가짜 run 에는 확인 전 그림이 있다 → 마무리 확인 창에서 "그대로 진행"
    const downloadP = page.waitForEvent("download");
    await page.getByRole("button", { name: "HWPX 내려받기" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "그대로 진행" }).click();
    const download = await downloadP;
    expect(download.suggestedFilename()).toMatch(/^proposal-.*-v3\.hwpx$/);
    await expect(page.getByText("마무리됨")).toBeVisible();

    // 제안자 정보는 어디에도 저장되지 않는다
    const stored = await page.evaluate(() => JSON.stringify({ s: { ...sessionStorage }, l: { ...localStorage } }));
    expect(stored).not.toContain("홍길동");
    expect(stored).not.toContain(process.env.RRA_E2E_TOKEN ?? "e2e-token-1234");

    // 다시 열기
    await page.getByRole("button", { name: /다시 열기/ }).click();
    await expect(page.getByText("수정 중").first()).toBeVisible();
  });

  test("추천 0건 경로: '원래 아이디어로 진행' 으로 보강 질문 화면까지", async ({ page }) => {
    await login(page);
    await fillIdea(page, " (추천 없음)");
    await page.getByRole("button", { name: "유사과제 확인" }).click();
    await expect(page.getByText("추천 0건")).toBeVisible();
    await page.getByRole("button", { name: "원래 아이디어로 진행" }).click();
    await expect(page).toHaveURL(/\/new\/brief$/);
    await page.getByRole("button", { name: /다음: 보강 질문/ }).click();
    await expect(page).toHaveURL(/\/new\/clarify$/);
    await expect(page.getByText("보강 질문 없음")).toBeVisible();
  });

  test("보강 질문 건너뛰기(0개)는 바로 생성 버튼 하나", async ({ page }) => {
    await login(page);
    await fillIdea(page);
    await page.getByRole("button", { name: "유사과제 확인" }).click();
    await page.getByRole("button", { name: /다음: 선행연구 브리핑/ }).click();
    await page.getByRole("button", { name: /다음: 보강 질문/ }).click();
    await expect(page.getByRole("button", { name: "건너뛰고 생성" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "초안 생성 시작" })).toBeVisible();
  });

  test("run 목록·자료 검색·자료원 상태", async ({ page }) => {
    await login(page);
    await page.getByRole("link", { name: "run 목록" }).click();
    await expect(page.getByRole("table").or(page.getByText("아직 run 이 없습니다"))).toBeVisible();
    await page.getByRole("link", { name: "자료 검색" }).click();
    await page.getByLabel("검색어").fill("궤도");
    await page.getByRole("button", { name: "검색" }).click();
    await expect(page.getByText("비신뢰").first()).toBeVisible();
    await page.getByRole("link", { name: "자료원 상태" }).click();
    await expect(page.getByText("알리오 공시 연구보고서")).toBeVisible();
  });

  test("CSP 아래에서 콘솔 오류 없음", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
    page.on("pageerror", (e) => errors.push(e.message));
    await login(page);
    await fillIdea(page);
    await page.getByRole("button", { name: "유사과제 확인" }).click();
    await expect(page).toHaveURL(/precheck/);
    expect(errors).toEqual([]);
  });
});
