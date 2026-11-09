import { describe, expect, it } from "vitest";
import type { PrecheckAlert } from "@/api/types-precheck";
import { ApiError } from "@/api/client";
import { expectedMode, isModeChanged, modeMismatch, planKey, planSignature } from "./model";

// ② 과제안 갈래 전환 (2026-11-09 레인 B, ADR 0061) — 서버 similar_rows.recommend_mode 와 같은 규칙:
// novel = [유사함] 0건(선택 없는 행은 AI 기본 선택) AND 차단 없음(차단 게이트는 제안자 선택만).
const alert = (doc_id: string, blocking = false) =>
  ({ doc_id, title: doc_id, tier: "own", similarity: 0.9, blocking }) as unknown as PrecheckAlert;
const plain = [alert("own:1"), alert("own:2")];
const defaults = [
  { doc_id: "own:1", choice: "similar" as const },
  { doc_id: "own:2", choice: "unrelated" as const },
];
const withBlock = [alert("alio:b", true), alert("own:2")];

describe("expectedMode", () => {
  it("기본 [유사함] 이 있으면 차별화, 그 행을 [관련 없음] 으로 바꾸면 novel (a·b 전환)", () => {
    expect(expectedMode({}, defaults, plain)).toBe("differentiate");
    expect(expectedMode({ "own:1": "unrelated" }, defaults, plain)).toBe("novel");
    // (a) novel 화면에서 다시 [유사함] 으로 → 차별화
    expect(expectedMode({ "own:1": "similar" }, defaults, plain)).toBe("differentiate");
  });

  it("차단 행은 제안자가 [관련 없음] 으로 고르기 전까지 차별화 — 미리 고른 값은 차단을 풀지 않는다", () => {
    const d = [{ doc_id: "alio:b", choice: "similar" as const }];
    expect(expectedMode({}, d, withBlock)).toBe("differentiate");
    expect(expectedMode({ "alio:b": "unrelated" }, d, withBlock)).toBe("novel");
    // 판정·선택이 없는 차단 행(규칙 판정)만 있어도 차단이라 차별화
    expect(expectedMode({}, [], withBlock)).toBe("differentiate");
    expect(expectedMode({ "alio:b": "unrelated" }, [], withBlock)).toBe("novel");
  });

  it("알림이 없으면 novel", () => {
    expect(expectedMode({}, [], [])).toBe("novel");
  });
});

describe("planKey", () => {
  it("갈래 + 유사함 서명 — 유사함 집합이 같아도 갈래가 바뀌면 열쇠가 다르다", () => {
    // 차단 행(판정 없음)을 [관련 없음] 으로 — 유사함 서명은 둘 다 "" 이지만 차별화 → novel
    expect(planSignature({}, [], withBlock)).toBe(planSignature({ "alio:b": "unrelated" }, [], withBlock));
    expect(planKey({}, [], withBlock)).toBe("differentiate:");
    expect(planKey({ "alio:b": "unrelated" }, [], withBlock)).toBe("novel:");
    expect(planKey({}, defaults, plain)).toBe("differentiate:own:1");
  });
});

describe("modeMismatch · isModeChanged", () => {
  it("화면의 과제안 갈래(mode 없으면 차별화)와 지금 선택의 갈래가 다른가", () => {
    expect(modeMismatch({ mode: "novel" }, { "own:1": "unrelated" }, defaults, plain)).toBe(false);
    expect(modeMismatch({ mode: "novel" }, {}, defaults, plain)).toBe(true); // (a) novel → 차별화
    expect(modeMismatch({ mode: "differentiate" }, { "own:1": "unrelated" }, defaults, plain)).toBe(true); // (b) 차별화 → novel
    expect(modeMismatch({ mode: "differentiate" }, {}, defaults, plain)).toBe(false);
    expect(modeMismatch(null, {}, defaults, plain)).toBe(false);
    // 갈래를 모르는 응답(mode 없음, 옛 서버)은 전환으로 보지 않는다 — 서버 판정에 맡긴다
    expect(modeMismatch({}, { "own:1": "unrelated" }, defaults, plain)).toBe(false);
    // 서버가 novel 을 차별화로 되돌린 과제안(novelty_reverted)은 novel 입력의 답 — 전환 아님 (되풀이 방지)
    expect(modeMismatch({ mode: "differentiate", novelty_reverted: true }, { "own:1": "unrelated" }, defaults, plain)).toBe(false);
    expect(modeMismatch({ mode: "differentiate", novelty_reverted: true }, {}, defaults, plain)).toBe(false);
  });

  it("서버 409 code=mode_changed 만 갈래 전환으로 본다", () => {
    const changed = new ApiError({ type: "about:blank", title: "상태 충돌", status: 409, detail: "선택이 바뀌어 과제안을 다시 받습니다.", code: "mode_changed" });
    const other = new ApiError({ type: "about:blank", title: "상태 충돌", status: 409, detail: "새 과제안은 [과제안 다시 만들기]로 새로 받습니다." });
    expect(isModeChanged(changed)).toBe(true);
    expect(isModeChanged(other)).toBe(false);
    expect(isModeChanged(new Error("x"))).toBe(false);
    expect(isModeChanged(null)).toBe(false);
  });
});
