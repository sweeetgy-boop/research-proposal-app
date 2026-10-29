import { defineConfig, devices } from "@playwright/test";

// e2e 는 백엔드 가짜 모드(RRA_FAKE_LLM=1)가 web/dist 를 서빙하는 상태로 돈다 (실제 CSP·쿠키·SSE 경로 그대로).
// 먼저 `npm run build`. 백엔드 실행 파일은 RRA_BIN(저장소 루트 기준, 기본 .venv/bin/rra), 포트 8010.
const PORT = Number(process.env.RRA_E2E_PORT ?? 8010);
const RRA_BIN = process.env.RRA_BIN ?? ".venv/bin/rra"; // 저장소 루트 기준 (webServer 가 cd .. 한 뒤 실행)
const TOKEN = process.env.RRA_E2E_TOKEN ?? "e2e-token-1234";
const FIGURE_DELAY = process.env.RRA_FAKE_FIGURE_DELAY ?? "3";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
    video: process.env.RRA_VIDEO ? "on" : "off",
    locale: "ko-KR",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    // 가짜 그림은 장마다 잠깐 기다린다(ADR 0045) — 초안이 먼저 보이고 "그림 준비 중" 카드가 보이는 흐름을 그대로 시험한다
    command: `cd .. && RRA_FAKE_LLM=1 RRA_FAKE_FIGURE_DELAY=${FIGURE_DELAY} RRA_API_TOKEN=${TOKEN} RRA_STATIC_DIR=web/dist ${RRA_BIN} api --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/healthz`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
