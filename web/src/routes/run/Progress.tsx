import * as React from "react";
import { useLocation, useNavigate } from "react-router";
import { useMutation } from "@tanstack/react-query";
import { Check, CircleDashed, Loader2, SkipForward, X } from "lucide-react";
import { useRunContext } from "./useRunContext";
import { isActive } from "@/api/hooks";
import { resumeRun } from "@/api/endpoints";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ProblemBanner } from "@/components/ProblemBanner";
import { stepLabel, statusLabel } from "@/lib/sections";
import { cn } from "@/lib/utils";
import { SectionsSoFar } from "@/features/progress/SectionsSoFar";
import { figuresDrawing } from "@/features/figures/figureJob";

export default function Progress() {
  const { run, refetch } = useRunContext();
  const navigate = useNavigate();
  const location = useLocation();
  const [done, total] = run.progress;
  const pct = total ? Math.round((done / total) * 100) : 0;
  const resume = useMutation({ mutationFn: () => resumeRun(run.run_id), onSuccess: () => refetch() });

  // 생성이 끝나면 초안 화면으로 (생성 직후 도착했거나 진행 중일 때만 — 진행 탭을 직접 열었을 때는 그대로 둔다)
  const created = !!(location.state as { created?: boolean } | null)?.created;
  const autoNav = React.useRef(isActive(run.status) || created);
  React.useEffect(() => {
    if (autoNav.current && !isActive(run.status) && !["failed", "invalid", "interrupted"].includes(run.status)) {
      autoNav.current = false;
      navigate(`/runs/${run.run_id}/draft`, { replace: true });
    }
  }, [run.status, run.run_id, navigate]);

  const generating = run.status === "queued" || run.status === "running";
  // ADR 0045 — 초안 글이 보인 뒤에도 그림 단계는 백그라운드로 돈다
  const drawing = figuresDrawing(run);

  return (
    <div className="space-y-6">
      <section aria-labelledby="progress-h" className="space-y-3">
        <h2 id="progress-h" className="text-lg font-semibold">
          ③ 초안 생성 — {statusLabel(run.status)}
        </h2>
        <div
          role="progressbar"
          aria-label="초안 생성 진행률"
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={done}
          aria-valuetext={`${total} 단계 중 ${done} 완료`}
          className="h-2.5 w-full overflow-hidden rounded-full bg-primary-soft"
        >
          <div className="h-full rounded-full bg-primary transition-[width] duration-300" style={{ width: `${pct}%` }} />
        </div>
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {generating
            ? `${done}/${total} 단계 완료 — ${run.writer === "gemini" ? "Argon 이" : "로컬 모델이"} 섹션을 쓰는 중입니다. 다 쓴 섹션은 아래에 먼저 보입니다.`
            : run.status === "draft_reviewing"
              ? "Argon 1차 검토 중 — 통과한 수정안만 v2 에 자동 반영됩니다."
              : run.status === "final_reviewing"
                ? "Argon 최종 검토 중입니다."
                : `${done}/${total} 단계`}
        </p>
      </section>

      {run.status === "failed" && (
        <Alert variant="destructive" role="alert">
          <X aria-hidden="true" />
          <div>
            <AlertTitle>생성 실패</AlertTitle>
            <AlertDescription>{run.steps.find((s) => s.error)?.error ?? "단계 오류 — 아래 목록에서 확인하십시오."}</AlertDescription>
          </div>
        </Alert>
      )}
      {run.status === "invalid" && (
        <Alert variant="destructive" role="alert">
          <X aria-hidden="true" />
          <div>
            <AlertTitle>입력 오류</AlertTitle>
            <AlertDescription>입력이 규칙에 맞지 않아 생성하지 못했습니다. 새 제안서로 다시 입력하십시오.</AlertDescription>
          </div>
        </Alert>
      )}
      {run.status === "interrupted" && (
        <Alert variant="warning">
          <CircleDashed aria-hidden="true" />
          <div className="flex-1">
            <AlertTitle>중단됨</AlertTitle>
            <AlertDescription>서버가 멈춰 생성이 끊겼습니다. 이어서 할 수 있습니다.</AlertDescription>
            <ProblemBanner error={resume.error} className="mt-2" />
            <Button className="mt-3" onClick={() => resume.mutate()} disabled={resume.isPending}>
              {resume.isPending ? "요청 중…" : "이어서 생성"}
            </Button>
          </div>
        </Alert>
      )}

      <SectionsSoFar runId={run.run_id} generating={generating} />

      <section aria-labelledby="steps-h">
        <h3 id="steps-h" className="mb-2 text-base font-semibold">
          단계 {run.steps.length}개
        </h3>
        <ol className="divide-y rounded-lg border">
          {run.steps.map((s) => (
            <li key={s.name} className="flex items-center gap-3 px-3 py-2 text-sm">
              <span className="inline-flex size-5 items-center justify-center" aria-hidden="true">
                {s.status === "done" ? (
                  <Check className="size-4 text-success" />
                ) : s.status === "error" ? (
                  <X className="size-4 text-destructive" />
                ) : s.status === "skipped" ? (
                  <SkipForward className="size-4 text-muted-foreground" />
                ) : (generating && run.steps.findIndex((x) => x.status === "pending") === run.steps.indexOf(s)) || (drawing && s.name === "figures") ? (
                  <Loader2 className="size-4 animate-spin text-primary" />
                ) : (
                  <CircleDashed className="size-4 text-muted-foreground" />
                )}
              </span>
              <span className={cn("flex-1", s.status === "pending" && "text-muted-foreground")}>
                {stepLabel(s.name)}
                {drawing && s.name === "figures" && " — 그림 준비 중 (초안 글은 먼저 볼 수 있습니다)"}
              </span>
              <span className="sr-only">
                {s.status === "done" ? "완료" : s.status === "error" ? "오류" : s.status === "skipped" ? "건너뜀" : "대기"}
              </span>
              {s.error && <span className="text-xs text-destructive">{s.name === "figures" ? "일부 그림을 그리지 못했습니다 — 초안의 그림 카드에서 다시 그릴 수 있습니다" : s.error}</span>}
            </li>
          ))}
        </ol>
      </section>

      {!isActive(run.status) && !["failed", "invalid", "interrupted"].includes(run.status) && (
        <div className="flex justify-end">
          <Button onClick={() => navigate(`/runs/${run.run_id}/draft`)}>초안 보기 →</Button>
        </div>
      )}
    </div>
  );
}
