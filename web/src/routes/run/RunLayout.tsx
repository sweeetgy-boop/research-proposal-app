import * as React from "react";
import { NavLink, Outlet, useLocation, useParams } from "react-router";
import { Copy } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { isActive, keys, useRun } from "@/api/hooks";
import { subscribeRunEvents } from "@/api/sse";
import type { RunState } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Stepper } from "@/components/Stepper";
import { isEditable, isGenerated, runStepFromSub, runStepTargets } from "@/lib/runSteps";
import { reviewSkipLabel } from "@/lib/labels";
import { ProblemBanner } from "@/components/ProblemBanner";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { statusLabel } from "@/lib/sections";
import { cn } from "@/lib/utils";
import { useToast } from "@/components/ui/toast";
import { RunStepBar } from "@/features/stepnav/RunStepBar";

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
  { to: "submit-check", label: "제출 전 점검" },
  { to: "finalize", label: "최종 마무리" },
];

function statusVariant(s: string): "default" | "secondary" | "destructive" | "success" | "warning" | "info" {
  if (s === "failed" || s === "invalid") return "destructive";
  if (s === "interrupted") return "warning";
  if (s === "finalized") return "success";
  if (isActive(s as RunState["status"])) return "info";
  return "secondary";
}

/** [3] 작성자 — 눈에 덜 띄게 outline. 로컬로 넘어간 섹션이 있으면 "Argon 작성(일부 로컬)" (항목 21). */
function WriterChip({ run }: { run: RunState }) {
  if (!run.writer) return null;
  const locals = run.local_sections?.length ?? 0;
  if (run.writer === "local") {
    return (
      <Badge variant="outline" className="font-normal text-muted-foreground" title="이 제안서는 로컬 모델이 작성했습니다">
        로컬 작성
      </Badge>
    );
  }
  if (run.writer !== "gemini") return null;
  return (
    <Badge variant="outline" className="font-normal text-muted-foreground" title={locals ? `Argon 이 작성, ${locals}개 섹션은 Argon 실패 뒤 로컬 모델이 작성` : "Argon 이 작성했습니다"}>
      {locals ? "Argon 작성(일부 로컬)" : "Argon 작성"}
    </Badge>
  );
}

export default function RunLayout() {
  const { id = "" } = useParams();
  const q = useRun(id, { poll: true });
  const qc = useQueryClient();
  const { toast } = useToast();
  const run = q.data;
  const active = isActive(run?.status);
  const { pathname } = useLocation();
  const sub = pathname.replace(/^\/runs\/[^/]+\/?/, "").split("/")[0];

  const copyId = async () => {
    if (!run) return;
    try {
      await navigator.clipboard.writeText(run.run_id);
      toast("작성 번호를 복사했습니다.", "success");
    } catch {
      toast("복사하지 못했습니다 — 번호를 직접 선택해 복사하십시오.");
    }
  };

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

  const generated = isGenerated(run);
  const editable = isEditable(run);
  const title = (run.title ?? "").trim();
  const skipped = reviewSkipLabel(run.flow.draft_review_skipped, run.flow.draft_review_skipped_label);
  const enabledFor = (to: string): boolean => {
    if (to === "") return true;
    if (!generated) return false;
    if (to === "edit") return editable;
    return true;
  };

  return (
    <div className="space-y-5">
      <header className="space-y-2">
        <h1 className="text-xl font-bold leading-snug tracking-tight sm:text-2xl">
          {/* 두 줄까지 보이고 넘치면 말줄임 — 마우스(title)·키보드 초점(펼침)으로 전체 */}
          <span
            tabIndex={0}
            title={title || undefined}
            data-testid="run-title"
            className="line-clamp-2 break-words rounded-sm focus:line-clamp-none focus-visible:outline-2 focus-visible:outline-ring"
          >
            {title || "제목 미정"}
          </span>
        </h1>
        <p className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
          <span>작성 번호</span>
          <span className="font-mono">{run.run_id}</span>
          <Button type="button" variant="ghost" size="sm" className="h-7 px-2" onClick={copyId} aria-label="작성 번호 복사">
            <Copy className="size-3.5" aria-hidden="true" />
            복사
          </Button>
        </p>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="sr-only">작성 상태:</span>
          <Badge variant={statusVariant(run.status)}>{statusLabel(run.status)}</Badge>
          <span className="text-sm text-muted-foreground">v{run.draft_version}</span>
          <WriterChip run={run} />
          {run.legacy && <Badge variant="outline">예전 방식 (조회 전용)</Badge>}
          {run.flow.stale && (
            <Badge variant="warning" role="status">
              최종 검토 이후 수정 {run.flow.stale_edits}건
            </Badge>
          )}
          {skipped && <Badge variant="outline">{skipped}</Badge>}
          {run.flow.has_working && <Badge variant="info">임시 저장 있음</Badge>}
        </div>
      </header>
      <Stepper current={runStepFromSub(sub)} base={`/runs/${run.run_id}`} targets={runStepTargets(run)} />
      <nav aria-label="제안서 화면 메뉴" className="relative -mx-1 overflow-x-auto border-b">
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
      <RunStepBar run={run} sub={sub} />
    </div>
  );
}
