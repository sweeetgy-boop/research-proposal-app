import { AlertTriangle, ImageIcon, Loader2, RefreshCw } from "lucide-react";
import type { FigureKindV2, FigureSlot } from "@/api/types";
import { AiCancelledNote, AiWaiting } from "@/components/AiWaiting";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { ProblemBanner } from "@/components/ProblemBanner";
import { useAddFigureAi, useRetryTechniquesAi } from "./api";

export interface FigureSlotCardProps {
  runId: string;
  slot: FigureSlot;
  baseVersion: number;
  /** [다시 그리기] 비활성 (임시 편집 중·옛 버전·예전 제안서) */
  disabled?: boolean;
  onApplied: (version: number) => void;
}

/** 그림 자리 카드 (ADR 0045) — 그리는 중이면 "그림 준비 중", 실패·걸러짐이면 사유 + [다시 그리기].
 *  분석 기법 추천 자리는 [다시 그리기] 가 [다시 추천] 이다. 다 그리면 자리는 사라지고 그림 카드가 그 자리에 온다. */
export function FigureSlotCard({ runId, slot, baseVersion, disabled, onApplied }: FigureSlotCardProps) {
  const add = useAddFigureAi(runId);
  const retry = useRetryTechniquesAi(runId);
  const technique = slot.kind === "technique";
  const call = technique ? retry : add;
  const headingId = `slot-h-${slot.slot_id}`;
  const drawing = slot.status === "drawing";

  const redraw = async () => {
    const out = technique
      ? await retry.run({ base_version: baseVersion })
      : await add.run({ kind: slot.kind as FigureKindV2, section: slot.section, base_version: baseVersion });
    const version = out && "version" in out ? out.version : undefined;
    if (typeof version === "number") onApplied(version);
  };

  return (
    <Card role="group" aria-labelledby={headingId} data-testid="figure-slot" data-status={slot.status} className="border-dashed">
      <CardHeader className="gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <h4 id={headingId} className="text-sm font-semibold">
            {slot.display_name}
          </h4>
          {drawing ? (
            <Badge variant="info">
              <Loader2 className="mr-1 size-3 animate-spin" aria-hidden="true" />
              그림 준비 중
            </Badge>
          ) : (
            <Badge variant={slot.status === "failed" ? "destructive" : "secondary"}>
              <AlertTriangle className="mr-1 size-3" aria-hidden="true" />
              그리지 못함
            </Badge>
          )}
        </div>
        <div
          className="flex w-full items-center justify-center rounded border bg-muted/40 text-muted-foreground"
          style={{ aspectRatio: "21 / 9" }}
          aria-hidden="true"
        >
          {drawing ? <Loader2 className="size-6 animate-spin" /> : <ImageIcon className="size-6" />}
        </div>
        <p className="text-sm text-muted-foreground" role={drawing ? "status" : undefined}>
          {drawing ? "초안 글은 먼저 보고 고칠 수 있습니다. 그림은 준비되는 대로 이 자리에 들어갑니다." : (slot.reason_label ?? "그림을 그리지 못했습니다.")}
        </p>
      </CardHeader>
      {!drawing && (
        <>
          <CardContent className="space-y-2">
            <ProblemBanner error={call.error} />
            <AiCancelledNote show={call.cancelled} />
            <AiWaiting pending={call.pending} elapsed={call.elapsed} onCancel={call.cancel} what={technique ? "분석 기법 다시 추천" : "그림 다시 그리기"} />
          </CardContent>
          <CardFooter>
            <Button size="sm" variant="outline" onClick={redraw} disabled={!!disabled || call.pending} aria-label={`${slot.display_name} ${technique ? "다시 추천" : "다시 그리기"}`}>
              <RefreshCw aria-hidden="true" />
              {technique ? "다시 추천" : "다시 그리기"}
            </Button>
          </CardFooter>
        </>
      )}
    </Card>
  );
}
