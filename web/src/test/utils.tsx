import * as React from "react";
import { render, type RenderOptions } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import axe from "axe-core";
import { ToastProvider } from "@/components/ui/toast";

export function renderWithProviders(ui: React.ReactElement, { route = "/", path = "*", ...opts }: RenderOptions & { route?: string; path?: string } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <ToastProvider>
          <Routes>
            <Route path={path} element={children} />
          </Routes>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
  return { qc, ...render(ui, { wrapper, ...opts }) };
}

/** axe-core 실행 — WCAG 2.x A/AA 규칙. 위반 0건이어야 한다. */
export async function expectNoA11yViolations(container: Element): Promise<void> {
  const result = await axe.run(container, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] },
    rules: { "color-contrast": { enabled: false }, region: { enabled: false } }, // jsdom 은 색을 계산하지 못한다. region 은 화면 조각만 렌더해서 제외
  });
  const msgs = result.violations.map((v) => `${v.id}: ${v.help}\n  ${v.nodes.map((n) => n.html).join("\n  ")}`);
  expect(msgs, msgs.join("\n")).toEqual([]);
}

/** fetch 를 경로별로 가짜 응답으로 바꾼다. */
export type MockRoute = unknown | ((init?: RequestInit) => unknown);
export function mockFetch(routes: Record<string, MockRoute>) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    calls.push({ url, init });
    const key = Object.keys(routes).find((k) => url === k || url.startsWith(k + "?") || (k.endsWith("*") && url.startsWith(k.slice(0, -1))));
    if (!key) {
      return new Response(JSON.stringify({ type: "about:blank", title: "없음", status: 404, detail: `mock 없음: ${url}` }), {
        status: 404,
        headers: { "content-type": "application/problem+json" },
      });
    }
    const v = routes[key];
    const body = typeof v === "function" ? (v as (init?: RequestInit) => unknown)(init) : v;
    if (body instanceof Response) return body;
    return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return { fn, calls };
}

export function problem(status: number, detail: string): Response {
  return new Response(JSON.stringify({ type: "about:blank", title: "오류", status, detail }), {
    status,
    headers: { "content-type": "application/problem+json" },
  });
}
