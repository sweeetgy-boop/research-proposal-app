import * as React from "react";
import { NavLink, Outlet, useParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { isActive, keys, useRun } from "@/api/hooks";
import { subscribeRunEvents } from "@/api/sse";
import type { RunState } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { ProblemBanner } from "@/components/ProblemBanner";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { statusLabel } from "@/lib/sections";
import { cn } from "@/lib/utils";
import { useToast } from "@/components/ui/toast";

export interface RunContext {
  run: RunState;
  refetch: () => void;
}

const SUBNAV = [
  { to: "", label: "진행", end: true },
  { to: "draft", label: "초안 보기" },
  { to: "edit", label: "직접 수정" },
  { to: "versions", label: "버전·비교" },
  { to: "final-review", label: "최종 검토" },
  { to: "finalize", label: "최종 마무리" },
];

const EDITABLE = new Set(["drafted", "editing", "final_reviewed"]);

function statusVariant(s: string): "default" | "secondary" | "destructive" | "success" | "warning" | "info" {
  if (s === "failed" || s === "invalid") return "destructive";
  if (s === "interrupted") return "warning";
  if (s === "finalized") return "success";
  if (isActive(s as RunState["status"])) return "info";
  return "secondary";
}

export default function RunLayout() {
  const { id = "" } = useParams();
  const q = useRun(id, { poll: true });
  const qc = useQueryClient();
  const { toast } = useToast();
  const run = q.data;
  const active = isActive(run?.status);

  // SSE: 활성 상태(생성·검토 중)일 때만 구독. 상태를 캐시에 바로 넣고 이름 이벤트는 토스트.
  React.useEffect(() => {
    if (!id || !active) return;
    return subscribeRunEvents(id, {
      onState: (s) => qc.setQueryData(keys.run(id), s),
      onEvent: (ev) => {
        if (ev.name === "draft_ready") toast(`초안 v${ev.data.version} 이 준비되었습니다.`, "success");
        if (ev.name === "final_review_ready") toast("최종 검토 결과가 나왔습니다.", "success");
      },
      onEnd: () => qc.invalidateQueries({ queryKey: keys.run(id) }),
    });
  }, [id, active, qc, toast]);

  if (q.isPending) {
    return (
      <div className="space-y-4" aria-busy="true">
        <SkeletonBlock lines={2} />
        <SkeletonBlock lines={6} />
      </div>
    );
  }
  if (q.error || !run) return <ProblemBanner error={q.error} onRetry={() => q.refetch()} />;

  const generated = !["queued", "running", "failed", "invalid", "interrupted"].includes(run.status);
  const editable = EDITABLE.has(run.status);
  const enabledFor = (to: string): boolean => {
    if (to === "") return true;
    if (!generated) return false;
    if (to === "edit") return editable;
    return true;
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h1 className="text-xl font-bold tracking-tight sm:text-2xl">
          run <span className="font-mono text-base sm:text-lg">{run.run_id}</span>
        </h1>
        <Badge variant={statusVariant(run.status)}>{statusLabel(run.status)}</Badge>
        <span className="text-sm text-muted-foreground">v{run.draft_version}</span>
        {run.legacy && <Badge variant="outline">옛 run (조회 전용)</Badge>}
        {run.flow.stale && (
          <Badge variant="warning" role="status">
            최종 검토 이후 수정 {run.flow.stale_edits}건
          </Badge>
        )}
        {run.flow.draft_review_skipped && <Badge variant="outline">1차 검토 건너뜀 ({run.flow.draft_review_skipped})</Badge>}
        {run.flow.has_working && <Badge variant="info">임시 저장 있음</Badge>}
      </div>
      <nav aria-label="run 하위 메뉴" className="relative -mx-1 overflow-x-auto border-b">
        <ul className="flex min-w-max gap-1">
          {SUBNAV.map((s) => {
            const enabled = enabledFor(s.to);
            return (
              <li key={s.to}>
                {enabled ? (
                  <NavLink
                    to={s.to}
                    end={s.end}
                    className={({ isActive: on }) =>
                      cn(
                        "-mb-px inline-flex min-h-10 items-center border-b-2 px-3 text-sm font-medium",
                        on ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground",
                      )
                    }
                  >
                    {s.label}
                  </NavLink>
                ) : (
                  <span className="inline-flex min-h-10 items-center border-b-2 border-transparent px-3 text-sm text-muted-foreground/60" aria-disabled="true">
                    {s.label}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      </nav>
      <Outlet context={{ run, refetch: () => q.refetch() } satisfies RunContext} />
    </div>
  );
}
