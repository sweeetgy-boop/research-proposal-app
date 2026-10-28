import { expect, type Locator, type Page } from "@playwright/test";

/** 화면에 내부 번호가 보이면 안 된다 (ADR 0040) — 문서·청크 번호(own:…·alio:sum-…·ntis:…·korail_web:…),
 *  공개 요약 번호(sum-…), 그림 번호(f:method:t1·f:method:2), 문장 번호(s:objective:0).
 *  web/src/lib/docRefs.ts 의 hasInternalId 와 같은 기준. 통합 담당이 모든 화면에서 부른다:
 *    await expectNoInternalIds(page)                 // 본문 전체 (보이는 글만)
 *    await expectNoInternalIds(page, dialogLocator)  // 대화상자 등 일부만 */
const SOURCES = ["own", "alio", "ntis", "scienceon", "openalex", "kipris_kr", "kipris_intl", "korail_web", "molit", "rnd_notice", "g2b", "bai", "mofe", "datago"];
export const INTERNAL_ID_PATTERNS: RegExp[] = [
  new RegExp(`\\b(?:${SOURCES.join("|")}):[A-Za-z0-9_\\-.:/]*[A-Za-z0-9_\\-]`),
  /\bsum-[0-9a-f]{6,}/,
  /\bf:[a-z_]+:t?\d+\b/,
  /\bs:[a-z_]+:\d+\b/,
];

/** 보이는 글에서 내부 번호를 찾는다 — 찾은 조각 목록 */
export function findInternalIds(text: string): string[] {
  const out: string[] = [];
  for (const re of INTERNAL_ID_PATTERNS) {
    const g = new RegExp(re.source, "g");
    for (const m of text.matchAll(g)) out.push(m[0]);
  }
  return out;
}

export async function expectNoInternalIds(page: Page, scope?: Locator): Promise<void> {
  const target = scope ?? page.locator("body");
  await expect(target.first()).toBeVisible();
  const text = await target.first().innerText();
  const found = findInternalIds(text);
  expect(found, `화면에 내부 번호가 보입니다: ${found.slice(0, 5).join(", ")}`).toEqual([]);
}
