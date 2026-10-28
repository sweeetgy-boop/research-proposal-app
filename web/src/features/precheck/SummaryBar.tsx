import { CheckCircle2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AiWaiting } from "@/components/AiWaiting";

/** ② 선택 요약 막대 — 화면 아래에 붙어 스크롤해도 보인다 (ADR 0039).
 *  "유사함 n건 · 관련 없음 m건 → [선택 적용] [차별화 과제안 더 만들기]". 선택이 바뀌면 [선택 적용] 이 다시 켜지고
 *  지금 비교표가 예전 선택 기준임을 알린다. 아래 단계 막대(레인 D) 높이 `--stepnav-h` 위에 놓인다. */
export function SummaryBar({
  similar,
  unrelated,
  stale,
  applied,
  applying,
  onApply,
  onMore,
  moreDisabled,
  morePending,
  moreElapsed,
  onCancelMore,
}: {
  similar: number;
  unrelated: number;
  /** 지금 선택이 마지막 [선택 적용] 과 다르다 */
  stale: boolean;
  /** 한 번이라도 적용했다 (적용됨 문구) */
  applied: boolean;
  applying: boolean;
  onApply: () => void;
  onMore: () => void;
  moreDisabled: boolean;
  morePending: boolean;
  moreElapsed: number;
  onCancelMore: () => void;
}) {
  return (
    <div
      data-testid="precheck-summary-bar"
      className="sticky z-20 -mx-4 border-t bg-background/95 px-4 py-2 shadow-[0_-2px_6px_rgba(0,0,0,0.06)] backdrop-blur supports-[backdrop-filter]:bg-background/80 sm:mx-0 sm:rounded-lg sm:border"
      style={{ bottom: "var(--stepnav-h, 0px)" }}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <p className="text-sm font-medium" aria-live="polite">
          유사함 <span className="tabular-nums">{similar}</span>건 · 관련 없음 <span className="tabular-nums">{unrelated}</span>건
        </p>
        <span aria-hidden="true" className="text-muted-foreground">
          →
        </span>
        <Button size="sm" onClick={onApply} disabled={!stale || applying} variant={stale ? "default" : "outline"}>
          {applying ? "적용 중…" : "선택 적용"}
        </Button>
        <Button size="sm" variant="outline" onClick={onMore} disabled={moreDisabled || morePending}>
          <Plus aria-hidden="true" />
          차별화 과제안 더 만들기
        </Button>
        <span role="status" className="text-xs text-muted-foreground">
          {stale ? (
            "선택이 바뀌었습니다 — 비교표·활용 제안은 아직 이전 선택 기준입니다"
          ) : applied ? (
            <span className="inline-flex items-center gap-1 text-foreground">
              <CheckCircle2 className="size-3.5" aria-hidden="true" />
              선택 적용됨 · 비교표 갱신
            </span>
          ) : null}
        </span>
      </div>
      <AiWaiting pending={morePending} elapsed={moreElapsed} onCancel={onCancelMore} what="과제안 더 만들기" className="mt-1" />
    </div>
  );
}
