import { AlertTriangle, Loader2 } from "lucide-react";
import type { RunState } from "@/api/types";
import { FigureSlotCard } from "./FigureSlotCard";
import { figureJobOf } from "./figureJob";

export interface FigureJobBannerProps {
  run: RunState;
  /** 다 그린 그림 수 (현재 버전) */
  ready: number;
  baseVersion: number;
  disabled?: boolean;
  onApplied: (version: number) => void;
}

/** 그림 작업 한 줄 (ADR 0045) — 그리는 동안 "그림 준비 중 · n장 준비됨", 섹션을 아직 모르는 분석 기법 추천
 *  자리는 여기에 카드로. 서버가 다시 시작돼 끊겼으면 사유와 [다시 그리기](섹션 카드). 끝났으면 아무것도 없다. */
export function FigureJobBanner({ run, ready, baseVersion, disabled, onApplied }: FigureJobBannerProps) {
  const job = figureJobOf(run);
  const unplaced = job.figure_slots.filter((s) => !s.section);
  const drawing = job.figures_status === "pending" || job.figures_status === "drawing";
  const waiting = job.figure_slots.filter((s) => s.status === "drawing").length;
  if (!drawing && job.figures_status !== "failed" && unplaced.length === 0) return null;
  return (
    <section aria-label="그림 준비 상태" className="space-y-2 rounded-lg border border-dashed p-3 text-sm" data-testid="figure-job">
      {drawing ? (
        <p role="status" aria-live="polite" className="flex flex-wrap items-center gap-2">
          <Loader2 className="size-4 animate-spin text-primary" aria-hidden="true" />
          <span className="font-medium">그림 준비 중</span>
          <span className="text-muted-foreground">
            {ready}장 준비됨{waiting ? ` · ${waiting}장 그리는 중` : ""} — 초안 글은 지금 보고 고칠 수 있습니다. 최종 검토·마무리는 그림이 끝난 뒤에 할 수 있습니다.
          </span>
        </p>
      ) : job.figures_status === "failed" ? (
        <p role="alert" className="flex flex-wrap items-center gap-2">
          <AlertTriangle className="size-4 text-destructive" aria-hidden="true" />
          <span className="font-medium">그림을 모두 그리지 못했습니다</span>
          <span className="text-muted-foreground">그리지 못한 그림 카드의 [다시 그리기]로 다시 요청할 수 있습니다. 초안 글은 그대로입니다.</span>
        </p>
      ) : null}
      {unplaced.length > 0 && (
        <ul className="grid gap-3 md:grid-cols-2">
          {unplaced.map((s) => (
            <li key={s.slot_id} className="min-w-0">
              <FigureSlotCard runId={run.run_id} slot={s} baseVersion={baseVersion} disabled={disabled} onApplied={onApplied} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
