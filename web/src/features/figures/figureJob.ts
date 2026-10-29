/** 그림 백그라운드 작업(ADR 0045) — 제안서 상태의 그림 작업 필드를 읽는 도우미와 훅. */
import { useQuery } from "@tanstack/react-query";
import { getSectionsProgress } from "@/api/endpoints-progress";
import type { FigureJobFields, FigureSlot, RunState, RunWithFigureJob } from "@/api/types";
import { drawingFigures } from "@/lib/runSteps";

export function figureJobOf(run: RunState | undefined | null): FigureJobFields {
  const r = (run ?? {}) as RunWithFigureJob;
  return {
    figures_status: r.figures_status ?? null,
    figure_slots: r.figure_slots ?? [],
    draft_visible_seconds: r.draft_visible_seconds ?? null,
    figures_done_seconds: r.figures_done_seconds ?? null,
  };
}

/** 그림을 그리는 중 (pending·drawing) — 화면은 2초마다 다시 읽고, 최종 검토·마무리는 기다린다 */
export function figuresDrawing(run: RunState | undefined | null): boolean {
  return !!run && drawingFigures(run);
}

/** 그림 작업이 바뀌었는지 알아보는 표식 — 바뀌면 초안·그림 목록을 다시 읽는다 */
export function figureJobSignature(run: RunState | undefined | null): string {
  const job = figureJobOf(run);
  return `${job.figures_status ?? "-"}|${job.figure_slots.map((s) => `${s.slot_id}:${s.status}`).join(",")}`;
}

/** 한 섹션의 자리 카드 (그리는 중·실패·걸러짐) */
export function slotsFor(run: RunState | undefined | null, section: string): FigureSlot[] {
  return figureJobOf(run).figure_slots.filter((s) => s.section === section);
}

/** ③ 생성 중 — 끝난 섹션 글을 2초마다 */
export function useSectionsProgress(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ["run", id, "sections-progress"] as const,
    queryFn: ({ signal }) => getSectionsProgress(id, signal),
    enabled: enabled && !!id,
    refetchInterval: enabled ? 2000 : false,
  });
}
