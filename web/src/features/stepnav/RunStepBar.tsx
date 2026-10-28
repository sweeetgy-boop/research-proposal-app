import type { RunState } from "@/api/types";
import { useSubmitCheck } from "@/api/hooks";
import { StepNavBar } from "@/components/StepNavBar";
import { isGenerated, remainingWork, runStepNeighbors } from "@/lib/runSteps";

/** run 안 단계 화면(①~⑥)의 아래 이동 막대 — 이전·다음은 위쪽 단계 표시와 같은 표(runStepTargets),
 *  가운데는 제출 전 점검에서 아직 남은 일(확인 전 그림·추천 그림 결정·로컬 검토 불일치 …). */
export function RunStepBar({ run, sub }: { run: RunState; sub: string | undefined }) {
  const generated = isGenerated(run);
  const check = useSubmitCheck(run.run_id, generated && !run.legacy);
  const { current, prev, next } = runStepNeighbors(run, sub);
  if (current === null) return null;
  const base = `/runs/${run.run_id}`;
  const path = (to: string | null) => (to === null ? null : to ? `${base}/${to}` : base);
  // 남은 일은 ③ 이후(초안이 있을 때)만
  const remaining = current >= 3 && generated ? remainingWork(check.data?.items) : [];
  return (
    <StepNavBar
      prev={prev ? { label: `이전 단계: ${prev.label}`, to: path(prev.to), reason: prev.reason } : null}
      next={next ? { label: `다음: ${next.label}`, to: path(next.to), reason: next.reason } : null}
      remaining={remaining}
      noticeKey={`${run.run_id}:${current}`}
    />
  );
}
