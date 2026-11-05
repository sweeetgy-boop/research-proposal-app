import { describe, expect, it } from "vitest";
import type { PrecheckAlert } from "@/api/types-precheck";
import { choicesSignature, planSignature } from "./model";

// 과제안 서명은 서버가 실제로 쓴 선택(선택 없는 행은 AI 기본 선택)으로 — ADR 0054·0057 통합(2026-11-05)
const alert = (doc_id: string) => ({ doc_id, title: doc_id, tier: "own", similarity: 0.9, blocking: false }) as unknown as PrecheckAlert;
const alerts = [alert("own:1"), alert("own:2")];
const defaults = [
  { doc_id: "own:1", choice: "similar" as const },
  { doc_id: "own:2", choice: "unrelated" as const },
];

describe("planSignature", () => {
  it("선택이 없으면 AI 기본 선택의 [유사함] 으로 서명한다", () => {
    expect(planSignature({}, defaults, alerts)).toBe("own:1");
    expect(choicesSignature({})).toBe(""); // 종전 서명은 빈 문자열이라 아래 변화를 놓쳤다
  });

  it("기본 [유사함] 행을 [관련 없음] 으로 바꾸면 서명이 달라진다 → [선택 적용] 이 과제안을 다시 받는다", () => {
    const before = planSignature({}, defaults, alerts);
    const after = planSignature({ "own:1": "unrelated" }, defaults, alerts);
    expect(after).toBe("");
    expect(after).not.toBe(before);
  });

  it("제안자 선택이 기본 선택보다 앞선다", () => {
    expect(planSignature({ "own:2": "similar" }, defaults, alerts)).toBe("own:1|own:2");
  });
});
