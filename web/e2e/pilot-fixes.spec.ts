import { expect, test } from "@playwright/test";
import { fillIdea, login, subnav } from "./helpers";

/** 시범 오류·개선 17건 전체 경로 (통합 담당, 2026-10-28, 가짜 모드):
 *  ② 유사함·관련 없음 선택 → 비교표 → 차별화 과제안 고르기 → 보강 질문(정책 근거 작성안 선택) → 생성 →
 *  변경 없이 저장 팝업 → AI 다시 쓰기·보완 질문 → 그림 추천 넣기·빼기 → 저장 → 단계 표시 이동 → 최종 검토 →
 *  제출 전 점검 → 마무리(파일 이름). 레인별 세부 시험은 precheck-flow·edit-ai·figures·format-ui.spec.ts. */
test("17건 전체 경로: ② 선택 → 과제안 → 정책 작성안 → 생성 → 다시 쓰기·보완 질문 → 그림 추천 → 저장 팝업 → 단계 이동 → 점검 → 마무리", async ({
  page,
}) => {
  test.setTimeout(180_000);
  await page.setViewportSize({ width: 1280, height: 900 });
  await login(page);

  // ② 유사과제 — 차단 행 [관련 없음] → 해제, 다른 행 [유사함] → 비교표
  await fillIdea(page, " (중복)");
  await page.getByRole("button", { name: "유사과제 확인" }).click();
  await expect(page).toHaveURL(/\/new\/precheck$/);
  const next = page.getByRole("button", { name: /다음: 선행연구 브리핑/ });
  await expect(next).toBeDisabled();
  await expect(page.getByText(/차단 경보를 확인해 주세요/)).toBeVisible();
  const rows = page.getByRole("table", { name: /유사과제 목록/ }).locator("tbody tr");
  await rows.filter({ has: page.getByText("차단", { exact: true }) }).first().getByRole("button", { name: "관련 없음" }).click();
  await expect(next).toBeEnabled();
  await rows.filter({ hasNot: page.getByText("차단 해제") }).first().getByRole("button", { name: "유사함" }).click();
  await expect(page.getByRole("table", { name: /차별성 비교표/ })).toBeVisible();

  // 차별화 과제안 고르기
  await page.getByRole("button", { name: "이 안으로 진행" }).first().click();
  await expect(page.getByText(/과제안 1번을 입력에 반영했습니다/).first()).toBeVisible();
  await next.click();
  await expect(page).toHaveURL(/\/new\/brief$/);
  await page.getByRole("button", { name: /다음: 보강 질문/ }).click();
  await expect(page).toHaveURL(/\/new\/clarify$/);

  // 보강 질문 — 정책적 중요도 작성안 고르기
  await expect(page.getByText(/질문 \d개/)).toBeVisible();
  const cards = page.getByRole("list", { name: "정책적 중요도 작성안 목록" });
  await expect(cards.getByText("정부 계획", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "이 안으로 — 공사 전략" }).click();
  await expect(page.getByText("고른 정책 근거: 작성안 그대로")).toBeVisible();
  await page.getByRole("button", { name: /답하고 생성 시작|초안 생성 시작/ }).click();
  await expect(page.getByRole("heading", { name: "초안 본문" })).toBeVisible({ timeout: 30_000 });
  const id = /\/runs\/([0-9a-f-]+)/.exec(page.url())![1]!;
  // 정책적 중요도 빈칸 아님 (고른 작성안 그대로)
  await expect(page.getByText("인용 자료가 제시한 방향과 본 제안의 해결 목표가 이어짐.").first()).toBeVisible();
  // 머리에 과제 제목, run 번호는 작게
  await expect(page.getByTestId("run-title")).not.toHaveText("제목 미정");

  // ④ 직접 수정 — 변경 없이 저장 → 팝업 [취소]
  await subnav(page, "직접 수정").click();
  await expect(page).toHaveURL(new RegExp(`/runs/${id}/edit$`));
  await page.getByRole("button", { name: "새 버전으로 저장" }).click();
  const none = page.getByRole("dialog", { name: "변경된 내용이 없습니다" });
  await expect(none.getByText("변경된 내용이 없습니다. 최종 검토로 넘어갈까요?")).toBeVisible();
  await none.getByRole("button", { name: "취소" }).click();
  await expect(page).toHaveURL(new RegExp(`/runs/${id}/edit$`));

  // AI 다시 쓰기 (Argon) — 후보 1개 이상
  await page.getByRole("button", { name: "2-다 연구 방법 및 주요내용 AI 다시 쓰기" }).click();
  const rw = page.getByRole("dialog", { name: /AI 다시 쓰기 — 2-다/ });
  await expect(rw.getByText(/Argon 이 같은 지시·근거로 다시 씁니다/)).toBeVisible();
  await expect(rw.getByText(/새 후보 [1-9]\d*문장/)).toBeVisible();
  await rw.getByRole("button", { name: "닫기", exact: true }).last().click();

  // 보완 질문 (Argon) → 답 반영해 다시 쓰기
  await page.getByRole("button", { name: "2-가-(2) 기술적 중요도 보완 질문" }).click();
  const qd = page.getByRole("dialog", { name: /보완 질문 — 2-가-\(2\)/ });
  await expect(qd.getByText("Argon 이 본문을 읽고 물음")).toBeVisible();
  await qd.getByLabel(/국외 선행연구는/).fill("독일 DB 가 예측 정비를 도입함");
  await qd.getByRole("button", { name: /답 반영해 다시 쓰기/ }).click();
  const rw2 = page.getByRole("dialog", { name: /AI 다시 쓰기 — 2-가-\(2\)/ });
  await expect(rw2.getByText(/새 후보 [1-9]\d*문장/)).toBeVisible();
  await rw2.getByRole("button", { name: "닫기", exact: true }).last().click();

  // 그림 추천 — 넣기 확정·필요 없음
  await expect(page.getByText("분석 기법 추천: 추천함")).toBeVisible();
  await page.getByRole("button", { name: "SWOT 분석 넣기 확정" }).click();
  // 추천 그림 결정은 상태 표시 — 새 버전 없음, "확인 n건" 으로 센다 (항목 21)
  await expect(page.getByText("확인 표시를 저장했습니다 (새 버전 없음)").first()).toBeVisible();
  await page.getByRole("button", { name: "비용-편익 분석 필요 없음" }).click();
  await expect(page.getByRole("group", { name: "비용-편익 분석" })).toHaveCount(0);
  await expect(page.getByTestId("confirm-count")).toContainText(/확인 [1-9]\d*건/);

  // 바뀐 내용이 없으면 "변경된 내용이 없습니다. 최종 검토로 넘어갈까요?" → [확인]
  await page.getByRole("button", { name: "새 버전으로 저장" }).click();
  const saved = page.getByRole("dialog", { name: /저장했습니다|변경된 내용이 없습니다/ });
  await expect(saved.getByText(/최종 검토로 넘어갈까요\?/)).toBeVisible();
  await saved.getByRole("button", { name: "확인" }).click();
  await expect(page).toHaveURL(new RegExp(`/runs/${id}/final-review$`));

  // 단계 표시 이동 — ① 아이디어 입력을 run 안에서 보고 돌아오기, ⑥ 은 아직 닫힘
  const steps = page.getByRole("navigation", { name: "작성 단계" });
  await expect(steps.getByRole("link", { name: /최종 마무리/ })).toHaveAttribute("aria-disabled", "true");
  await steps.getByRole("link", { name: /아이디어 입력/ }).click();
  await expect(page).toHaveURL(new RegExp(`/runs/${id}/idea$`));
  await expect(page.getByLabel(/현재 상황·문제/)).toHaveValue(/궤도 틀림/);
  await steps.getByRole("link", { name: /최종 검토/ }).click();
  await expect(page).toHaveURL(new RegExp(`/runs/${id}/final-review$`));

  // ⑤ 최종 검토 → 제출 전 점검 (한국어 설명·일괄 승인·제안값 확정)
  await page.getByRole("button", { name: "최종 검토 요청" }).click();
  await expect(page.getByRole("heading", { name: /Argon 최종 검토/ })).toBeVisible({ timeout: 30_000 });
  await subnav(page, "제출 전 점검").click();
  await expect(page.getByRole("heading", { name: "제출 전 점검" })).toBeVisible();
  const bulk = page.getByRole("button", { name: /근거 일괄 승인/ });
  if (await bulk.isEnabled()) {
    await bulk.click();
    await expect(page.getByText(/근거 \d+건을 승인했습니다/).first()).toBeVisible();
  }
  const accept = page.getByRole("button", { name: "제안값 그대로 확정" });
  while ((await accept.count()) > 0 && (await accept.first().isEnabled())) {
    await accept.first().click();
    await expect(page.getByText(/로 확정했습니다/).first()).toBeVisible();
    await page.waitForTimeout(300);
  }
  const body = (await page.locator("main").textContent()) ?? "";
  expect(body).not.toMatch(/input_missing|policy_basis_needed|figures_undecided|self_review|no_change|warning|sections_sum/);

  // ⑥ 최종 마무리 — 파일 이름 "<과제 제목>_v<번호>.hwpx"
  await steps.getByRole("link", { name: /최종 마무리/ }).click();
  await expect(page).toHaveURL(new RegExp(`/runs/${id}/finalize$`));
  const downloadP = page.waitForEvent("download");
  await page.getByRole("button", { name: "HWPX 내려받기" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "그대로 진행" }).click({ timeout: 3_000 }).catch(() => undefined);
  const name = (await downloadP).suggestedFilename();
  expect(name).toMatch(/_v\d+\.hwpx$/);
  expect(name).not.toMatch(/^proposal-/);
});
