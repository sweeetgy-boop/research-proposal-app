import { defineConfig, devices } from "@playwright/test";

// e2e 는 백엔드 가짜 모드(RRA_FAKE_LLM=1)가 web/dist 를 서빙하는 상태로 돈다 (실제 CSP·쿠키·SSE 경로 그대로).
// 먼저 `npm run build`. 백엔드 실행 파일은 RRA_BIN(기본 ../.venv/bin/rra), 포트 8010.
const PORT = Number(process.env.RRA_E2E_PORT ?? 8010);
const RRA_BIN = process.env.RRA_BIN ?? "../.venv/bin/rra";
const TOKEN = process.env.RRA_E2E_TOKEN ?? "e2e-token-1234";

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
    command: `cd .. && RRA_FAKE_LLM=1 RRA_API_TOKEN=${TOKEN} RRA_STATIC_DIR=web/dist ${RRA_BIN} api --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/healthz`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
