/** [3] Argon 우선 작성 "로컬 작성" 배지 · [4] 실시간 검색 배지·자료원별 상태.
 *  가짜 백엔드(RRA_FAKE_LLM=1)는 아직 새 필드를 내지 않으므로(백엔드 레인 병렬 작업) 응답을 가로채 필드만 끼워 넣는다.
 *  RRA_SCREENS_DIR 가 있으면 화면 두 장을 남긴다. */
import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { createRun, fillIdea, login, subnav } from "./helpers";

const OUT = process.env.RRA_SCREENS_DIR ?? "";

const LIVE_SEARCH = {
  status: "partial",
  keywords: { ko: ["궤도 틀림", "검측 이력"], en: ["track geometry", "maintenance priority"] },
  sources: [
    { source: "scienceon", status: "ok", count: 7, seconds: 1.42, notice: null },
    { source: "ntis", status: "ip_blocked", count: 0, seconds: 0.31, notice: "NTIS 는 등록된 서버 IP 에서만 조회됩니다. 관리자에게 IP 등록을 요청하십시오." },
    { source: "openalex", status: "timeout", count: 0, seconds: 8.0, notice: null },
  ],
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Json = Record<string, any>;

async function injectLiveFields(page: Page) {
  await page.route(/\/v1\/precheck(\?.*)?$/, async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const res = await route.fetch();
    const body = (await res.json()) as Json;
    body.alerts = (body.alerts ?? []).map((a: Json, i: number) => ({ ...a, live: i === 0 }));
    body.related_research = [
      { doc_id: "scienceon:live-e2e-1", title: "실시간 검색 논문 (e2e)", source: "scienceon", source_label: "ScienceON 국내 논문·보고서", doc_type: "paper", year: 2025, similarity: 0.91, url: null, live: true },
      ...((body.related_research ?? []) as Json[]).map((r) => ({ ...r, live: false })),
    ];
    body.live_search = LIVE_SEARCH;
    await route.fulfill({ response: res, json: body });
  });
  // GET /v1/runs/{id} — run 머리 칩
  await page.route(
    (url) => /^\/v1\/runs\/[^/]+$/.test(url.pathname),
    async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      const res = await route.fetch();
      if (!res.ok()) return route.fulfill({ response: res });
      const body = (await res.json()) as Json;
      await route.fulfill({ response: res, json: { ...body, writer: "gemini", local_sections: ["objective"], live_search: LIVE_SEARCH } });
    },
  );
  // GET /v1/runs/{id}/draft (현재 버전만 — ?version= 은 그대로)
  await page.route(
    (url) => /^\/v1\/runs\/[^/]+\/draft$/.test(url.pathname) && !url.search,
    async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      const res = await route.fetch();
      if (!res.ok()) return route.fulfill({ response: res });
      const body = (await res.json()) as Json;
      body.writers = {
        title: { provider: "gemini", model: "gemini-argon", local_fallback: false, reason: null },
        objective: { provider: "mlx", model: "qwen2.5-7b", local_fallback: true, reason: "rate_limit" },
      };
      body.local_sections = ["objective"];
      body.local_check = { enabled: true, mismatches: 1, skipped_sections: [] };
      body.citations = (body.citations ?? []).map((c: Json, i: number) => ({ ...c, live: i === 0 }));
      body.problems = [
        ...(body.problems ?? []),
        { section: "objective", code: "local_evidence_mismatch", severity: "warning", message: "로컬 대조: 근거와 맞지 않는 문장이 있습니다", sentence: null },
      ];
      await route.fulfill({ response: res, json: body });
    },
  );
  // GET /v1/runs/{id}/sentences/{sid}/evidence
  await page.route(
    (url) => /^\/v1\/runs\/[^/]+\/sentences\/[^/]+\/evidence$/.test(url.pathname),
    async (route) => {
      const res = await route.fetch();
      if (!res.ok()) return route.fulfill({ response: res });
      const body = (await res.json()) as Json;
      body.evidence = (body.evidence ?? []).map((e: Json, i: number) => ({ ...e, live: i === 0 }));
      await route.fulfill({ response: res, json: body });
    },
  );
}

test("② 실시간 검색 배지·자료원별 상태 → 초안 로컬 작성 배지·근거 대조·근거 패널 실시간 배지", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await injectLiveFields(page);
  await login(page);
  await fillIdea(page, " (실시간)");
  await page.getByRole("button", { name: "유사과제 확인" }).click();
  await expect(page).toHaveURL(/\/new\/precheck$/);

  // 유사과제 표: 첫 행만 실시간 검색
  const alerts = page.getByRole("table", { name: "유사과제 목록" });
  await expect(alerts.getByRole("row").nth(1).getByText("실시간 검색", { exact: true })).toBeVisible();
  // 관련 연구: 실시간 항목
  const related = page.getByRole("region", { name: /관련 연구/ });
  await expect(related.getByRole("listitem").first().getByText("실시간 검색", { exact: true })).toBeVisible();
  // 자료원별 상태
  const status = page.getByRole("table", { name: "자료원별 상태" });
  await expect(status.getByRole("row", { name: /ScienceON/ })).toContainText("7건");
  await expect(status.getByRole("row", { name: /ScienceON/ })).toContainText("완료");
  await expect(status.getByRole("row", { name: /NTIS/ })).toContainText("IP 차단");
  await expect(status.getByRole("row", { name: /OpenAlex/ })).toContainText("시간 초과");
  await expect(page.getByText("NTIS 는 등록된 서버 IP 에서만 조회됩니다.", { exact: false })).toBeVisible();
  const keywords = page.locator("details", { has: page.getByText("검색어", { exact: true }) });
  await expect(keywords.getByText("track geometry")).toBeHidden();
  await keywords.getByText("검색어", { exact: true }).click();
  await expect(keywords.getByText("track geometry")).toBeVisible();
  if (OUT) {
    fs.mkdirSync(OUT, { recursive: true });
    await page.getByRole("region", { name: /실시간 검색/ }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(OUT, "2026-10-28-argon-live-01-precheck-live-search.png"), fullPage: true });
  }

  // 나머지 흐름은 그대로 (②→브리핑→보강 질문→생성)
  await page.getByRole("button", { name: /다음: 선행연구 브리핑/ }).click();
  await expect(page).toHaveURL(/\/new\/brief$/);
  await page.getByRole("button", { name: /다음: 보강 질문/ }).click();
  await expect(page).toHaveURL(/\/new\/clarify$/);
  await page.getByRole("button", { name: /초안 생성 시작|답하고 생성 시작/ }).click();
  await expect(page).toHaveURL(/\/runs\/[0-9a-f-]+(\/draft)?$/, { timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "초안 본문" })).toBeVisible({ timeout: 30_000 });

  // 초안 보기: 로컬 작성 배지(사유 호출 한도)·근거 대조(로컬)·run 머리 칩·인용 문서 실시간 배지
  const objective = page.getByRole("heading", { level: 3, name: /^2-나 연구목적/ });
  await expect(objective.getByText("로컬 작성", { exact: true })).toHaveAttribute("title", "이 섹션은 로컬 모델이 작성 (Argon 작성 실패: 호출 한도)");
  await expect(page.getByRole("heading", { level: 3, name: /^1-가 연구과제명/ }).getByText("로컬 작성", { exact: true })).toHaveCount(0);
  await expect(page.getByTestId("local-check")).toContainText("근거 대조(로컬) 불일치 1건");
  await expect(page.getByText("Argon 작성(일부 로컬)")).toBeVisible();
  await expect(page.getByRole("region", { name: /인용 문서/ }).getByText("실시간 검색", { exact: true }).first()).toBeVisible();
  if (OUT) {
    await objective.scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(OUT, "2026-10-28-argon-live-02-draft-local-badge.png"), fullPage: true });
  }

  // 근거 패널: 첫 근거에 실시간 검색 배지
  await page.getByRole("button", { name: /2-가-\(2\) 기술적 중요도 문장 1 근거 \d+건 보기/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "근거 보기" })).toBeVisible();
  await expect(dialog.getByText("실시간 검색", { exact: true }).first()).toBeVisible();
  await page.keyboard.press("Escape");

  // 직접 수정: 같은 배지
  await subnav(page, "직접 수정").click();
  await expect(page.getByRole("heading", { level: 3, name: /^2-나 연구목적/ }).getByText("로컬 작성", { exact: true })).toBeVisible();
});

test("새 필드가 없는 응답(옛 run)에서는 배지·패널 없이 기존 흐름 그대로", async ({ page }) => {
  // 옛 run 흉내: 백엔드(#71 이후)가 돌려주는 [3]·[4] 새 필드를 응답에서 뺀다
  const NEW_FIELDS = ["writer", "writers", "local_sections", "local_check", "live_search"];
  await page.route(/\/v1\/(runs\/[^/?]+(\/draft)?|precheck)(\?.*)?$/, async (route) => {
    const response = await route.fetch();
    const type = response.headers()["content-type"] ?? "";
    if (route.request().method() !== "GET" && !route.request().url().includes("/precheck")) return route.fulfill({ response });
    if (!type.includes("json")) return route.fulfill({ response });
    const json = await response.json();
    for (const k of NEW_FIELDS) delete json[k];
    return route.fulfill({ response, json });
  });
  await login(page);
  await createRun(page);
  await expect(page.getByText("로컬 작성", { exact: true })).toHaveCount(0);
  await expect(page.getByText("AI 작성", { exact: true }).first()).toBeVisible(); // 문장 origin llm
  await expect(page.getByTestId("local-check")).toHaveCount(0);
  await expect(page.getByText(/Argon 작성/)).toHaveCount(0);
  await expect(page.getByText("실시간 검색", { exact: true })).toHaveCount(0);
});
