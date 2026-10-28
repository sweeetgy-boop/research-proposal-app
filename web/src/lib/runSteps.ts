/** 위쪽 단계 표시(①~⑥)를 run 안에서 누를 때의 목적지와 "아직 못 여는 이유" (항목 17). 순수 함수.
 *  아래 탭(진행·초안 보기·직접 수정…)과 같은 경로로 가므로 단계를 누르면 그 탭이 켜진다. */
import type { RunState } from "@/api/types";

/** 전체 흐름 ①~⑥ — 위쪽 단계 표시·아래 이동 막대가 함께 쓰는 한 표 (항목 22) */
export const FLOW_STEPS = [
  { n: 1, label: "아이디어 입력", hint: "간편·상세, 정책 근거" },
  { n: 2, label: "유사과제 확인", hint: "추천·비교표·브리핑" },
  { n: 3, label: "초안 생성", hint: "근거 패널" },
  { n: 4, label: "직접 수정", hint: "다시 쓰기·보완 질문" },
  { n: 5, label: "최종 검토", hint: "제출 전 점검" },
  { n: 6, label: "최종 마무리", hint: "다운로드" },
] as const;

export const stepLabel = (n: number): string => FLOW_STEPS.find((s) => s.n === n)?.label ?? "";

export interface StepTarget {
  n: number;
  /** run 하위 경로 ("" = 진행). null 이면 아직 못 연다 */
  to: string | null;
  reason: string | null;
}

const NOT_GENERATED = new Set(["queued", "running", "failed", "invalid", "interrupted"]);
const EDITABLE = new Set(["drafted", "editing", "final_reviewed"]);

export const isGenerated = (run: Pick<RunState, "status">): boolean => !NOT_GENERATED.has(run.status);
export const isEditable = (run: Pick<RunState, "status">): boolean => EDITABLE.has(run.status);

/** ⑥ 최종 마무리를 할 수 있는가 — 최종 검토 완료(또는 마무리됨), 검토 모델이 없어 건너뛴 초안 */
export function canFinalize(run: RunState): { ok: boolean; reason: string | null } {
  const f = run.flow;
  if (run.legacy) return { ok: false, reason: "예전 방식으로 만든 제안서는 마무리할 수 없습니다." };
  if (f.has_working) return { ok: false, reason: "저장하지 않은 임시 편집이 있습니다. 직접 수정에서 저장하거나 버리십시오." };
  if (run.status === "final_reviewed" || run.status === "finalized") return { ok: true, reason: null };
  if ((run.status === "drafted" || run.status === "editing") && (f.draft_review_skipped === "no_review_llm" || f.final_reviews > 0))
    return { ok: true, reason: null };
  if (run.status === "drafted" || run.status === "editing") return { ok: false, reason: "최종 검토를 한 번 받은 뒤에 마무리할 수 있습니다 (검토 모델 키가 없으면 바로 가능)." };
  return { ok: false, reason: "생성·검토가 끝난 뒤에 마무리할 수 있습니다." };
}

function editReason(run: RunState): string {
  if (!isGenerated(run)) return "초안 생성 후 열립니다";
  if (run.status === "draft_reviewing" || run.status === "final_reviewing") return "검토가 끝난 뒤 열립니다";
  if (run.status === "finalized") return "마무리를 [다시 열기] 하면 고칠 수 있습니다";
  return "지금은 고칠 수 없습니다";
}

export function runStepTargets(run: RunState): StepTarget[] {
  const generated = isGenerated(run);
  const fin = canFinalize(run);
  return [
    { n: 1, to: "idea", reason: null },
    { n: 2, to: "precheck", reason: null },
    { n: 3, to: generated ? "draft" : "", reason: null },
    { n: 4, to: isEditable(run) ? "edit" : null, reason: isEditable(run) ? null : editReason(run) },
    { n: 5, to: generated ? "final-review" : null, reason: generated ? null : "초안 생성 후 열립니다" },
    {
      n: 6,
      to: generated && fin.ok ? "finalize" : null,
      reason: !generated ? "초안 생성 후 열립니다" : fin.ok ? null : run.flow.has_working ? "임시 편집을 저장한 뒤 열립니다" : "최종 검토 후 열립니다",
    },
  ];
}

/** run 하위 경로 → 단계 번호 (Layout 의 /new… 경로와 같은 표) */
export function runStepFromSub(sub: string | undefined): number | null {
  switch (sub) {
    case "idea":
      return 1;
    case "precheck":
      return 2;
    case undefined:
    case "":
    case "draft":
      return 3;
    case "edit":
    case "versions":
      return 4;
    case "final-review":
    case "submit-check":
      return 5;
    case "finalize":
      return 6;
    default:
      return null;
  }
}

/** ①·② 를 run 안에서 바꿔 다시 쓸 수 없는 이유 (없으면 null) */
export function changeBlockedReason(run: RunState): string | null {
  if (run.legacy) return "예전 방식으로 만든 제안서는 입력을 바꿔 다시 쓸 수 없습니다.";
  if (run.draft_version < 1) return "초안이 완성된 뒤에 입력을 바꿔 다시 쓸 수 있습니다. 지금은 보기만 합니다.";
  if (run.flow.has_working) return "저장하지 않은 임시 편집이 있습니다 — 직접 수정에서 저장하거나 버린 뒤 바꿀 수 있습니다.";
  if (!isEditable(run)) return run.status === "finalized" ? "마무리된 제안서입니다 — 최종 마무리에서 [다시 열기] 뒤 바꿀 수 있습니다." : "검토·생성이 끝난 뒤에 바꿀 수 있습니다. 지금은 보기만 합니다.";
  return null;
}

/** 아래 이동 막대의 한쪽 — to 가 null 이면 아직 못 간다(reason). */
export interface StepLink {
  n: number;
  label: string;
  to: string | null;
  reason: string | null;
}

/** run 안 화면의 이전·다음 단계 (위쪽 단계 표시와 같은 runStepTargets 를 쓴다 — 셋이 늘 같은 단계).
 *  ①·②(입력 다시 보기)도 run 안 화면이라 같은 표를 따른다. */
export function runStepNeighbors(run: RunState, sub: string | undefined): { current: number | null; prev: StepLink | null; next: StepLink | null } {
  const current = runStepFromSub(sub);
  if (current === null) return { current, prev: null, next: null };
  const targets = runStepTargets(run);
  const link = (n: number): StepLink | null => {
    const t = targets.find((x) => x.n === n);
    if (!t) return null;
    return { n, label: stepLabel(n), to: t.to, reason: t.to === null ? t.reason : null };
  };
  return { current, prev: link(current - 1), next: link(current + 1) };
}

/** 제출 전 점검 항목 → 막대 가운데의 "남은 일" 한 줄 (예: "확인 전 그림 1장 · 추천 그림 결정 1건").
 *  막지 않는다 — 넘어갈 때 한 번 알림만. 레인 B 의 로컬 검토 불일치 항목도 같은 방식으로 붙는다. */
export interface RemainingItem {
  key: string;
  label: string;
  ok: boolean;
  count?: number;
}

const REMAINING_LABELS: Record<string, (n: number) => string> = {
  figures_unconfirmed: (n) => `확인 전 그림 ${n}장`,
  figures_undecided: (n) => `추천 그림 결정 ${n}건`,
  evidence_approval: (n) => `근거 확인 ${n}건`,
  open_memos: (n) => `남은 메모 ${n}건`,
  unresolved_alerts: (n) => `알림 ${n}건`,
};

// 막대에 먼저 보일 항목 — 그림·추천 그림 결정·로컬 검토 불일치(레인 B 키 이름 후보)
const FIRST = ["figures_unconfirmed", "figures_undecided", "local_review_mismatch", "local_review", "local_check"];
const rank = (key: string) => {
  const i = FIRST.findIndex((k) => key === k || key.startsWith(k));
  return i < 0 ? FIRST.length : i;
};

export function remainingWork(items: RemainingItem[] | undefined, limit = 3): string[] {
  const out: string[] = [];
  const sorted = [...(items ?? [])].sort((a, b) => rank(a.key) - rank(b.key));
  for (const i of sorted) {
    if (i.ok) continue;
    const n = i.count ?? 0;
    const fmt = REMAINING_LABELS[i.key];
    out.push(fmt && n > 0 ? fmt(n) : n > 0 ? `${i.label} ${n}건` : i.label);
  }
  return out.length > limit ? [...out.slice(0, limit), `외 ${out.length - limit}건`] : out;
}
