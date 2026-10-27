import { emptyRequest, summarizeErrors, supplementFromAnswers, validateRequest } from "./validation";

describe("validateRequest", () => {
  it("필수 4개가 비면 백엔드와 같은 문구", () => {
    const errs = validateRequest(emptyRequest());
    expect(Object.keys(errs).sort()).toEqual(["current_state", "goal", "limitation", "root_cause"]);
    expect(summarizeErrors(errs)).toBe("필수 슬롯이 비었습니다: 현재 상황·문제, 발생 원인, 현행 대응의 한계, 해결 목표");
  });
  it("공백만 있어도 비어 있음", () => {
    expect(validateRequest({ ...emptyRequest(), current_state: "  " }).current_state).toBeDefined();
  });
  it("길이 상한 2000·200", () => {
    const req = { ...emptyRequest(), current_state: "a".repeat(2001), root_cause: "b", limitation: "c", goal: "d", title_hint: "t".repeat(201) };
    const errs = validateRequest(req);
    expect(errs.current_state).toBe("슬롯 길이 2001 > 2000");
    expect(errs.title_hint).toBe("길이 201 > 200");
    expect(summarizeErrors(errs)).toContain("가제: 길이 201 > 200");
  });
  it("유효하면 오류 없음", () => {
    expect(validateRequest({ ...emptyRequest(), current_state: "a", root_cause: "b", limitation: "c", goal: "d" })).toEqual({});
    expect(summarizeErrors({})).toBeNull();
  });
  it("예산 금액은 0 이상 정수", () => {
    const req = { ...emptyRequest(), current_state: "a", root_cause: "b", limitation: "c", goal: "d", budget: { account: "x", amount_thousand_krw: -1 } };
    expect(validateRequest(req)["budget.amount_thousand_krw"]).toBeDefined();
  });
});

describe("supplementFromAnswers", () => {
  it("답한 것만 '질문: 답' 줄로", () => {
    expect(supplementFromAnswers([{ question: "대상 구간?", answer: "경부선" }, { question: "기간?", answer: " " }])).toBe("대상 구간?: 경부선");
  });
});
