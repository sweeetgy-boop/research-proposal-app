// Lighthouse CI 실행 — CHROME_PATH 가 없으면 Playwright 의 Chromium 을 쓴다 (네트워크·백엔드 없이 vite preview 만).
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const env = { ...process.env };
if (!env.CHROME_PATH) {
  try {
    env.CHROME_PATH = require("playwright").chromium.executablePath();
  } catch {
    /* lhci 가 스스로 찾는다 */
  }
}
const r = spawnSync("npx", ["lhci", "autorun"], { stdio: "inherit", env, shell: process.platform === "win32" });
process.exit(r.status ?? 1);
