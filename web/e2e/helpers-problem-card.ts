import fs from "node:fs";
import path from "node:path";
import type { Page, Route } from "@playwright/test";

/** 문제 정의 카드 e2e — 진단·수정 두 경로의 가로채기를 이 파일 한 곳에 모은다 (ADR 0065, 계약 3절·7절).
 *  레인 C 를 만들 때는 서버(레인 A)가 없어 계약 형식 응답을 여기서 돌려준다. 통합 뒤 실제 서버(가짜 모드 + 설정 사본
 *  `enabled: true`)로 돌릴 때는 `RRA_E2E_REAL_CARD=1` — 가로채지 않고 요청 본문만 기록한다(route.continue).
 *  spec 은 afterEach 에서 `page.unrouteAll({ behavior: "ignoreErrors" })` 를 부른다. */
export const DIAGNOSE = "**/v1/ideas/diagnose";
export const DIAGNOSE_EDIT = "**/v1/ideas/diagnose/edit";
export const REAL_CARD = !!process.env.RRA_E2E_REAL_CARD;

type Json = Record<string, unknown>;
/** vitest 와 같은 계약 응답(서버 모델 검증을 통과하는 카드) — `npm run e2e` 는 web/ 에서 돈다 */
export const DIAGNOSE_OK = JSON.parse(fs.readFileSync(path.resolve("src/test/fixtures/problem_card.json"), "utf8")) as Json & {
  card: Json;
  lines: Record<string, string>;
};
export const DIAGNOSE_OFF: Json = { ...DIAGNOSE_OK, status: "off", card: null, lines: null, signal_labels: [], provider: null, model: null };

/** 수정된 항목 → 과제안이 옛 문제 정의 기준이 되는가 (서버 CARD_DEPENDENTS 의 plans_stale 과 같다) */
const STALE_FIELDS = new Set(["function_ko", "function_en", "ladder", "terms", "contradiction", "ipc"]);

/** 계약 3.2절 모양의 수정 응답 — after 를 그대로 받아 고친 항목만 제안자 수정으로 표시하고 4줄을 다시 만든다 */
export function fakeEditResponse(body: { before: Json; after: Json; fields: string[] }): Json {
  const card = structuredClone(body.after) as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  const before = body.before as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  if (body.fields.includes("function_ko")) Object.assign(card.function_ko, { origin: "user", ai_value: before.function_ko.value });
  if (body.fields.includes("cause") && card.causes[0]) Object.assign(card.causes[0], { origin: "user", ai_value: before.causes[0]?.value ?? "", needs_check: false });
  if (body.fields.includes("contradiction")) Object.assign(card.contradiction, { origin: "user", ai_improve: before.contradiction.improve, ai_worsen: before.contradiction.worsen });
  const codes = [...card.ipc, ...card.science_class].map((c: { code: string }) => c.code);
  return {
    card,
    lines: {
      function: card.function_ko.value,
      cause: card.causes[0]?.value ?? "",
      contradiction: card.contradiction.improve || card.contradiction.worsen ? `${card.contradiction.improve} ↔ ${card.contradiction.worsen}` : "",
      codes: codes.join(" · "),
    },
    reruns: body.fields.some((f) => STALE_FIELDS.has(f)) ? ["plans_stale"] : [],
    plans_stale: body.fields.some((f) => STALE_FIELDS.has(f)),
    recorded: true,
  };
}

export interface CardStub {
  /** 받은 진단 요청 본문 */
  diagnoses: Json[];
  /** 받은 수정 요청 본문 */
  edits: Json[];
  /** hold 로 붙잡아 둔 진단 응답을 푼다 */
  release: () => void;
}

/** 진단·수정 경로를 가로챈다.
 *  - diagnose: 진단 응답 몸통(기본 = 카드 있는 ok 응답). 숫자면 그 HTTP 상태의 오류 응답.
 *  - hold: true 면 release() 를 부를 때까지 진단 응답을 붙잡아 둔다(느린 진단). */
export async function stubProblemCard(page: Page, opts: { diagnose?: Json | number; hold?: boolean } = {}): Promise<CardStub> {
  let open: () => void = () => undefined;
  const gate = opts.hold ? new Promise<void>((r) => (open = r)) : Promise.resolve();
  const stub: CardStub = { diagnoses: [], edits: [], release: () => open() };
  const json = (route: Route, body: Json, status = 200) =>
    route.fulfill({ status, contentType: status === 200 ? "application/json" : "application/problem+json", body: JSON.stringify(body) });

  await page.route(DIAGNOSE, async (route) => {
    stub.diagnoses.push(route.request().postDataJSON() as Json);
    if (REAL_CARD) return route.continue();
    await gate;
    const d = opts.diagnose ?? DIAGNOSE_OK;
    if (typeof d === "number") return json(route, { type: "about:blank", title: "오류", status: d, detail: "가로챈 오류 응답" }, d);
    return json(route, d);
  });
  await page.route(DIAGNOSE_EDIT, async (route) => {
    const body = route.request().postDataJSON() as { before: Json; after: Json; fields: string[] };
    stub.edits.push(body);
    if (REAL_CARD) return route.continue();
    return json(route, fakeEditResponse(body));
  });
  return stub;
}

/** ① '핵심 문제' 카드 */
export function problemCard(page: Page) {
  return page.getByTestId("problem-card");
}
