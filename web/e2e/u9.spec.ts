/** U9 — 간편 입력 → 비교표 → 브리핑 → 생성 → 근거 패널·판단 → AI 다시 쓰기·보완 질문 → 최종 검토 → 제출 전 점검 → 다운로드 → 만족도.
 *  RRA_SCREENS_DIR 가 있으면 새 화면을 캡처한다 (docs/history/screens/2026-10-27-web-u9-NN.png). */
import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { login, subnav } from "./helpers";

const OUT = process.env.RRA_SCREENS_DIR ?? "";
async function shot(page: Page, n: number, name: string) {
  if (!OUT) return;
  fs.mkdirSync(OUT, { recursive: true });
  await page.screenshot({ path: path.join(OUT, `2026-10-27-web-u9-${String(n).padStart(2, "0")}-${name}.png`), fullPage: true });
}

test.describe("U9 사용성 흐름", () => {
  test("간편 입력 → 비교표 → 브리핑(우선 근거) → 생성 → 근거 패널 판단 → 다시 쓰기·보완 질문 → 최종 검토 → 제출 전 점검 → HWPX → 만족도", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await login(page);

    // ① 간편 입력 (기본 모드). 정책 근거 추천은 필수 4칸이 비어 있으면 버튼이 잠긴다
    await expect(page.getByRole("radio", { name: "간편 입력" })).toBeChecked();
    await expect(page.getByRole("button", { name: "추천 받기" })).toBeDisabled();
    await page.getByLabel(/아이디어를 한두 문장으로/).fill("궤도 틀림이 반복 발생함. 검측 이력 기반으로 보수 우선순위를 정하고 싶음.");
    await page.getByLabel("가제 (선택)").fill("궤도 보수 우선순위");
    await page.getByRole("button", { name: "네 칸으로 나누기" }).click();
    await expect(page.getByRole("heading", { name: "네 칸 미리보기" })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("궤도 틀림이 반복 발생함.").first()).toBeVisible();
    await shot(page, 1, "quick-input");
    // 보완 질문 2개(원인·한계) → 답 반영
    await page.getByLabel(/그 문제가 생기는 원인은/).fill("다짐 효과가 오래 가지 않음");
    await page.getByLabel(/지금 하고 있는 대응/).fill("주기적 보수로는 진행 속도를 반영하지 못함");
    await page.getByRole("button", { name: "답 반영" }).click();
    await expect(page.getByText("모두 채워짐")).toBeVisible();
    await page.getByRole("button", { name: /상세 입력에 채우기/ }).click();
    await expect(page.getByRole("radio", { name: "상세 입력(4칸)" })).toBeChecked();
    await expect(page.getByLabel(/발생 원인/)).toHaveValue("다짐 효과가 오래 가지 않음");
    await expect(page.getByLabel(/가제/)).toHaveValue("궤도 보수 우선순위");
    // 정책 근거 추천 — 엔드포인트가 없으면 접힌 안내. 가짜 저장소에 정책 문서 3건(레인 B) → 문구가 나온다
    await page.getByRole("button", { name: "추천 받기" }).click();
    await expect(
      page.getByText(/정책 근거 추천은 정책 자료 적재 뒤 열립니다|추천할 문구가 없습니다|정책 자료에서 찾은 문구입니다/),
    ).toBeVisible();
    await page.getByRole("button", { name: "유사과제 확인" }).click();

    // ② 유사과제·비교표
    await expect(page).toHaveURL(/\/new\/precheck$/);
    // 2026-10-28 레인 A: 비교표는 [유사함] 으로 고른 과제만 — 첫 행을 고른다
    await expect(page.getByText("유사한 과제를 고르면 비교표가 만들어집니다")).toBeVisible();
    await page.getByRole("table", { name: /유사과제 목록/ }).locator("tbody tr").first().getByRole("button", { name: "유사함" }).click();
    await page.getByRole("button", { name: "선택 적용" }).click(); // v3: [선택 적용] 으로 반영 (ADR 0039)
    await expect(page.getByRole("table", { name: /차별성 비교표/ })).toBeVisible();
    await expect(page.getByRole("rowheader", { name: /제안 과제/ })).toBeVisible();
    await shot(page, 2, "comparison");
    await page.getByRole("button", { name: /다음: 선행연구 브리핑/ }).click();

    // 브리핑 — 항목 체크 → priority_evidence
    await expect(page).toHaveURL(/\/new\/brief$/);
    await expect(page.getByRole("heading", { name: /선행연구 \d+건/ })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("후보").first()).toBeVisible();
    const firstBox = page.getByRole("checkbox").first();
    await firstBox.check();
    await expect(page.getByText("선택 1건")).toBeVisible();
    await shot(page, 3, "brief");
    const runReq = page.waitForRequest((r) => r.url().endsWith("/v1/runs") && r.method() === "POST");
    await page.getByRole("button", { name: /다음: 보강 질문/ }).click();
    await expect(page).toHaveURL(/\/new\/clarify$/);
    await page.getByRole("button", { name: /초안 생성 시작|답하고 생성 시작/ }).click();
    const body = (await runReq).postDataJSON() as { priority_evidence?: string[] };
    expect(body.priority_evidence).toHaveLength(1);

    // ③ 초안 → 근거 패널
    await expect(page.getByRole("heading", { name: "초안 본문" })).toBeVisible({ timeout: 30_000 });
    const id = /\/runs\/([0-9a-f-]+)/.exec(page.url())![1]!;
    await page.getByRole("button", { name: /2-가-\(2\) 기술적 중요도 문장 1 근거 \d+건 보기/ }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("heading", { name: "근거 보기" })).toBeVisible();
    await expect(dialog.getByText("세부 확인 필요")).toBeVisible();
    await expect(dialog.getByText("공개 요약")).toBeVisible();
    await shot(page, 4, "evidence-panel");
    await dialog.getByText("승인", { exact: true }).click();
    await dialog.getByRole("button", { name: "판단 저장" }).click();
    await expect(page.getByText(/근거 판단을 저장했습니다 \(새 버전 없음\)/).first()).toBeVisible(); // 항목 21
    await expect(dialog).toBeHidden();
    // Esc 로도 닫힌다
    await page.getByRole("button", { name: /2-나 연구목적 문장 1 근거 \d+건 보기/ }).click();
    await expect(dialog.getByText("이 문장에는 근거가 없습니다")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();

    // ④ 편집 — 보완 질문 → 답 저장, AI 다시 쓰기 → 반영
    await subnav(page, "직접 수정").click();
    await page.getByRole("button", { name: "2-다 연구 방법 및 주요내용 보완 질문" }).click();
    await expect(dialog.getByText(/체크리스트 충족/)).toBeVisible();
    await expect(dialog.getByText("Argon 이 본문을 읽고 물음")).toBeVisible(); // 보완 질문은 Argon (레인 B)
    await dialog.getByRole("textbox").first().fill("1차년도 분석 보고서");
    await dialog.getByRole("button", { name: "답 저장" }).click();
    await expect(page.getByText(/답을 저장했습니다/).first()).toBeVisible();
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "2-다 연구 방법 및 주요내용 AI 다시 쓰기" }).click();
    await expect(dialog.getByRole("table", { name: /현재 문장과 다시 쓴 후보/ })).toBeVisible({ timeout: 20_000 });
    await shot(page, 5, "rewrite");
    await dialog.getByRole("button", { name: /문장 반영/ }).click();
    await expect(page.getByText(/AI 다시 쓰기를 v3 으로 반영했습니다/).first()).toBeVisible();
    await expect(dialog).toBeHidden();

    // ⑤ 최종 검토 → 제출 전 점검
    await subnav(page, "최종 검토").click();
    await page.getByRole("button", { name: "최종 검토 요청" }).click();
    await expect(page.getByRole("heading", { name: /Argon 최종 검토/ })).toBeVisible({ timeout: 30_000 });
    await page.getByRole("link", { name: "제출 전 점검 →" }).click();
    await expect(page).toHaveURL(new RegExp(`/runs/${id}/submit-check$`));
    await expect(page.getByRole("heading", { name: "제출 전 점검" })).toBeVisible();
    await expect(page.getByRole("list", { name: "제출 전 점검 항목" })).toBeVisible();
    await expect(page.getByText("AI 다시 쓰기", { exact: true })).toBeVisible(); // 사용 기록
    await expect(page.getByText("최종 마무리(HWPX 내려받기) 뒤에 기록할 수 있습니다.")).toBeVisible();
    await shot(page, 6, "submit-check");
    // 항목 → 초안 보기 앵커로 이동
    await page.getByRole("button", { name: /미해결 알림: 확인 필요/ }).click();
    await expect(page).toHaveURL(new RegExp(`/runs/${id}/draft#sec-`));
    await page.goBack();

    // ⑥ 다운로드 → 만족도
    await page.getByRole("link", { name: "최종 마무리 →" }).click();
    await page.getByLabel("제안부서").fill("철도연구원");
    const downloadP = page.waitForEvent("download");
    await page.getByRole("button", { name: "HWPX 내려받기" }).click();
    // 근거 판단·다시 쓰기 뒤에도 그림이 버전에 남는다(레인 D 수정) → 확인 전 그림 확인창
    const proceed = page.getByRole("dialog").getByRole("button", { name: "그대로 진행" });
    await proceed.click({ timeout: 3_000 }).catch(() => undefined);
    const download = await downloadP;
    expect(download.suggestedFilename()).toMatch(/\.hwpx$/);
    await expect(page.getByText("마무리됨")).toBeVisible();
    await subnav(page, "제출 전 점검").click();
    await page.getByRole("radio", { name: "5" }).click();
    await page.getByLabel(/한 줄 소감/).fill("근거 패널이 유용함");
    await page.getByRole("button", { name: "만족도 보내기" }).click();
    await expect(page.getByText(/기록됨: 5\/5/)).toBeVisible();
    await shot(page, 7, "feedback");

    // 폰 너비·다크에서 가로 스크롤 없음 (제출 전 점검·브리핑)
    await page.getByRole("button", { name: /어두운 테마로 바꾸기/ }).click();
    await page.setViewportSize({ width: 360, height: 780 });
    await expect(page.getByRole("heading", { name: "제출 전 점검" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
    await shot(page, 8, "submit-check-dark-360");
  });

  test("간편 입력 503 이면 상세 입력으로 되돌린다 (가짜 503 라우트)", async ({ page }) => {
    await login(page);
    await page.route("**/v1/ideas/structure", (r) => r.fulfill({ status: 503, contentType: "application/problem+json", body: JSON.stringify({ type: "about:blank", title: "꺼짐", status: 503, detail: "간편 입력을 쓸 수 없습니다." }) }));
    await page.getByLabel(/아이디어를 한두 문장으로/).fill("궤도 틀림이 반복 발생함.");
    await page.getByRole("button", { name: "네 칸으로 나누기" }).click();
    await expect(page.getByRole("radio", { name: "상세 입력(4칸)" })).toBeChecked();
    await expect(page.getByLabel(/현재 상황·문제/)).toBeVisible();
  });
});
