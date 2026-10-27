import { Navigate, useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { SkipForward } from "lucide-react";
import { brief } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import { updateIdea, useIdea } from "@/features/idea/store";
import { BriefView } from "@/features/brief/BriefView";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { SKIP_LABELS } from "@/lib/sections";

/** ②와 ③ 사이 — 선행연구 브리핑. 건너뜀·503·오류여도 다음으로 갈 수 있다. */
export default function Brief() {
  const idea = useIdea();
  const navigate = useNavigate();
  const q = useQuery({
    queryKey: ["brief", idea.request],
    queryFn: () => brief(idea.request),
    enabled: !!idea.precheck,
    staleTime: Infinity,
    retry: false,
  });

  if (!idea.precheck) return <Navigate to="/new" replace />;
  if (idea.precheck.blocking && !idea.acknowledged) return <Navigate to="/new/precheck" replace />;

  const unavailable = isApiError(q.error) && q.error.status === 503;
  const skipped = q.data?.skipped_reason ?? null;
  const toggle = (id: string, on: boolean) =>
    updateIdea({ priorityEvidence: on ? [...new Set([...idea.priorityEvidence, id])] : idea.priorityEvidence.filter((x) => x !== id) });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">선행연구 브리핑</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          검색된 논문·보고서 상위 10건을 한 줄씩 요약하고 연도별 건수·주제어·연구 공백 후보를 보여 줍니다. 요약은 모델 출력이며, 후보는 확정이 아닙니다.
        </p>
      </div>

      {q.isPending ? (
        <div aria-busy="true" className="space-y-3">
          <p className="text-sm text-muted-foreground" aria-live="polite">브리핑을 만드는 중입니다…</p>
          <SkeletonBlock lines={6} />
        </div>
      ) : unavailable || skipped ? (
        <Alert variant="info">
          <SkipForward aria-hidden="true" />
          <div>
            <AlertTitle>브리핑 건너뜀</AlertTitle>
            <AlertDescription>
              {unavailable ? "브리핑을 쓸 수 없습니다 (꺼짐 또는 LLM 없음)." : SKIP_LABELS[skipped ?? ""] ?? `사유: ${skipped}`} 그대로 다음 단계로 갈 수 있습니다.
            </AlertDescription>
          </div>
        </Alert>
      ) : q.error ? (
        <>
          <ProblemBanner error={q.error} onRetry={() => q.refetch()} />
          <p className="text-sm text-muted-foreground">브리핑 없이 진행할 수 있습니다.</p>
        </>
      ) : q.data ? (
        <BriefView brief={q.data} selected={idea.priorityEvidence} onToggle={toggle} />
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-4">
        <Button variant="outline" onClick={() => navigate("/new/precheck")}>
          ← 유사과제 확인
        </Button>
        <Button onClick={() => navigate("/new/clarify")}>다음: 보강 질문 →</Button>
      </div>
    </div>
  );
}
