import { ClipboardCheck, RefreshCw } from "lucide-react";
import { useRunContext } from "./useRunContext";
import { isActive, useFinalReview, useStartFinalReview } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { ReviewPanel } from "@/features/draft/ReviewPanel";
import { EmptyState } from "@/components/EmptyState";
import { Link } from "react-router";
import { buttonVariants } from "@/components/ui/button";

const CAN_START = new Set(["drafted", "editing", "final_reviewed"]);

export default function FinalReview() {
  const { run } = useRunContext();
  const id = run.run_id;
  const review = useFinalReview(id, run.flow.final_reviews > 0 && !isActive(run.status));
  const start = useStartFinalReview(id);
  const reviewing = run.status === "final_reviewing";
  const blockedByWorking = run.flow.has_working;
  const canStart = CAN_START.has(run.status) && !blockedByWorking && !run.legacy;
  const skipped = run.flow.draft_review_skipped === "no_review_llm";

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">⑤ 최종 검토</h2>
          <p className="text-sm text-muted-foreground">최신 저장 버전(v{run.draft_version})을 Argon 이 최종 점검 관점으로 한 번 검토합니다. 이후 수정은 "최종 검토 이후 수정 n건"으로 표시됩니다.</p>
        </div>
        <Button onClick={() => start.mutate()} disabled={!canStart || start.isPending || reviewing}>
          {reviewing ? (
            <>
              <RefreshCw className="animate-spin" aria-hidden="true" /> 검토 중…
            </>
          ) : run.flow.final_reviews > 0 ? (
            <>
              <RefreshCw aria-hidden="true" /> 다시 받기 ({run.flow.final_reviews}회 받음)
            </>
          ) : (
            <>
              <ClipboardCheck aria-hidden="true" /> 최종 검토 요청
            </>
          )}
        </Button>
      </div>

      {run.flow.stale && (
        <Alert variant="warning" role="status">
          <RefreshCw aria-hidden="true" />
          <div>
            <AlertTitle>최종 검토 이후 수정 {run.flow.stale_edits}건</AlertTitle>
            <AlertDescription>검토한 v{run.flow.final_reviewed_version} 뒤에 본문이 바뀌었습니다. 다시 받을지는 선택입니다 — 마무리는 그대로 할 수 있습니다.</AlertDescription>
          </div>
        </Alert>
      )}
      {blockedByWorking && (
        <Alert variant="info">
          <ClipboardCheck aria-hidden="true" />
          <div>
            <AlertTitle>임시 저장이 남아 있습니다</AlertTitle>
            <AlertDescription>
              저장하지 않은 편집이 있으면 최종 검토를 요청할 수 없습니다.{" "}
              <Link to={`/runs/${id}/edit`} className="underline">직접 수정</Link>에서 저장하거나 버리십시오.
            </AlertDescription>
          </div>
        </Alert>
      )}
      {skipped && run.flow.final_reviews === 0 && (
        <Alert variant="info">
          <ClipboardCheck aria-hidden="true" />
          <div>
            <AlertTitle>검토 모델 키가 없습니다</AlertTitle>
            <AlertDescription>1차 검토가 건너뛰어졌습니다. 최종 검토 없이 바로 마무리할 수 있습니다.</AlertDescription>
          </div>
        </Alert>
      )}
      <ProblemBanner error={start.error} />

      {reviewing ? (
        <div aria-busy="true" className="space-y-2">
          <p className="text-sm text-muted-foreground" aria-live="polite">검토 결과를 기다리는 중입니다…</p>
          <SkeletonBlock lines={6} />
        </div>
      ) : run.flow.final_reviews === 0 ? (
        <EmptyState icon={ClipboardCheck} title="아직 최종 검토를 받지 않았습니다" description="직접 수정을 마친 뒤 요청하십시오. 결과에는 1차 대비 점수 변화가 함께 나옵니다." />
      ) : review.isPending ? (
        <SkeletonBlock lines={6} />
      ) : review.error ? (
        <ProblemBanner error={review.error} onRetry={() => review.refetch()} />
      ) : review.data ? (
        <div className="rounded-lg border p-3">
          <ReviewPanel review={review.data} title={`Argon 최종 검토 ${review.data.final_round ?? ""}차 (v${review.data.draft_version})`} />
          <div className="mt-4 flex flex-wrap gap-2">
            <Link to={`/runs/${id}/edit`} className={buttonVariants({ variant: "outline" })}>의견 반영하러 가기</Link>
            <Link to={`/runs/${id}/finalize`} className={buttonVariants()}>최종 마무리 →</Link>
          </div>
        </div>
      ) : null}
    </div>
  );
}
