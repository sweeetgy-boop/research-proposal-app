/** 위쪽 단계 표시(①~⑥)를 run 안에서 누를 때의 목적지와 "아직 못 여는 이유" (항목 17). 순수 함수.
 *  아래 탭(진행·초안 보기·직접 수정…)과 같은 경로로 가므로 단계를 누르면 그 탭이 켜진다. */
import type { RunState } from "@/api/types";

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
  if (run.legacy) return { ok: false, reason: "옛 run 은 마무리할 수 없습니다." };
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
  if (run.legacy) return "옛 run 은 입력을 바꿔 다시 쓸 수 없습니다.";
  if (run.draft_version < 1) return "초안이 완성된 뒤에 입력을 바꿔 다시 쓸 수 있습니다. 지금은 보기만 합니다.";
  if (run.flow.has_working) return "저장하지 않은 임시 편집이 있습니다 — 직접 수정에서 저장하거나 버린 뒤 바꿀 수 있습니다.";
  if (!isEditable(run)) return run.status === "finalized" ? "마무리된 run 입니다 — 최종 마무리에서 [다시 열기] 뒤 바꿀 수 있습니다." : "검토·생성이 끝난 뒤에 바꿀 수 있습니다. 지금은 보기만 합니다.";
  return null;
}
