/** 입력 검증 — 백엔드 domain/models/request.py 와 같은 규칙(필수 4개, 길이 2000/200). 문구도 같다. */
import type { ProposalRequest } from "@/api/types";

export const SLOT_MAX = 2000;
export const SHORT_MAX = 200;
export const REQUIRED_SLOTS = ["current_state", "root_cause", "limitation", "goal"] as const;
export const LONG_SLOTS = [
  "current_state",
  "root_cause",
  "limitation",
  "goal",
  "constraints",
  "policy_basis",
  "beneficiaries",
  "remarks",
  "differentiation",
  "supplement",
] as const;
export const SHORT_SLOTS = ["title_hint", "department"] as const;

export const FIELD_LABELS: Record<string, string> = {
  current_state: "현재 상황·문제",
  root_cause: "발생 원인",
  limitation: "현행 대응의 한계",
  goal: "해결 목표",
  constraints: "예산·기간·현장 제약",
  title_hint: "가제",
  policy_basis: "정책 근거",
  beneficiaries: "활용 주체 부서",
  remarks: "특이사항",
  differentiation: "차별화 방향",
  supplement: "보충 정보",
  department: "제안부서",
  "budget.account": "예산과목",
  "budget.amount_thousand_krw": "금액(천원)",
};

export type FieldErrors = Partial<Record<string, string>>;

export function emptyRequest(): ProposalRequest {
  return {
    current_state: "",
    root_cause: "",
    limitation: "",
    goal: "",
    constraints: "",
    title_hint: "",
    policy_basis: "",
    beneficiaries: "",
    remarks: "",
    differentiation: "",
    supplement: "",
    department: "",
    budget: null,
  };
}

export function validateRequest(req: ProposalRequest): FieldErrors {
  const errors: FieldErrors = {};
  for (const k of REQUIRED_SLOTS) {
    if (!(req[k] ?? "").trim()) errors[k] = "필수 슬롯이 비었습니다";
  }
  for (const k of LONG_SLOTS) {
    const v = (req[k] ?? "").trim();
    if (v.length > SLOT_MAX) errors[k] = `슬롯 길이 ${v.length} > ${SLOT_MAX}`;
  }
  for (const k of SHORT_SLOTS) {
    const v = (req[k] ?? "").trim();
    if (v.length > SHORT_MAX) errors[k] = `길이 ${v.length} > ${SHORT_MAX}`;
  }
  if (req.budget) {
    if ((req.budget.account ?? "").trim().length > SHORT_MAX) errors["budget.account"] = `길이 > ${SHORT_MAX}`;
    const amt = req.budget.amount_thousand_krw;
    if (amt !== null && amt !== undefined && (!Number.isInteger(amt) || amt < 0))
      errors["budget.amount_thousand_krw"] = "0 이상의 정수여야 합니다";
  }
  return errors;
}

/** 백엔드와 같은 한 줄 요약: "필수 슬롯이 비었습니다: a, b" */
export function summarizeErrors(errors: FieldErrors): string | null {
  const missing = REQUIRED_SLOTS.filter((k) => errors[k] === "필수 슬롯이 비었습니다");
  const parts: string[] = [];
  if (missing.length) parts.push(`필수 슬롯이 비었습니다: ${missing.map((k) => FIELD_LABELS[k] ?? k).join(", ")}`);
  for (const [k, msg] of Object.entries(errors)) {
    if (missing.includes(k as (typeof REQUIRED_SLOTS)[number])) continue;
    parts.push(`${FIELD_LABELS[k] ?? k}: ${msg}`);
  }
  return parts.length ? parts.join("; ") : null;
}

/** 보강 질문 답을 supplement 에 "질문: 답" 줄로 붙인다 */
export function supplementFromAnswers(pairs: { question: string; answer: string }[]): string {
  return pairs
    .filter((p) => p.answer.trim())
    .map((p) => `${p.question.trim()}: ${p.answer.trim()}`)
    .join("\n");
}
