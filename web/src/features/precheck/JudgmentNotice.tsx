import { RefreshCw, Sparkles, TriangleAlert } from "lucide-react";
import type { JudgmentInfo } from "@/api/types";
import { Button } from "@/components/ui/button";
import { AiWaiting } from "@/components/AiWaiting";

/** AI 같음 판정 안내. 표 먼저(ADR 0039): 판정을 기다리는 동안 "AI 판정 — 응답 기다리는 중 · 경과 n초 [취소]",
 *  취소·실패면 "규칙 기준" + [다시 시도]. 빈 결과로 끝내지 않는다. */
export function JudgmentNotice({
  judgment,
  coreKeywords,
  onRetry,
  retrying,
  elapsed = 0,
  onCancel,
  cancelled = false,
  defaultsAdded = 0,
}: {
  judgment: JudgmentInfo | undefined;
  coreKeywords?: string[];
  onRetry: () => void;
  /** AI 판정 호출 중 */
  retrying: boolean;
  elapsed?: number;
  onCancel?: () => void;
  /** 판정을 취소했다 (표는 규칙 기준 그대로) */
  cancelled?: boolean;
  /** AI "다르다" 로 [관련 없음] 을 미리 고른 행 수 */
  defaultsAdded?: number;
}) {
  if (!judgment) return null;
  const pendingState = judgment.status === "pending";
  const failed = judgment.retry_available || (pendingState && !retrying);
  const message = pendingState
    ? retrying
      ? "규칙 기준(관련도·핵심 키워드)으로 먼저 보입니다. AI 가 대상·문제·방법이 같은지 판정하는 중입니다."
      : cancelled
        ? "AI 판정을 취소했습니다 — 규칙 기준"
        : "AI 판정 전 — 규칙 기준"
    : judgment.message;
  return (
    <div
      role="status"
      className={`flex flex-wrap items-start justify-between gap-2 rounded-md border p-3 text-sm ${failed ? "border-warning/60" : ""}`}
      data-testid="judgment-notice"
    >
      <div className="flex items-start gap-2">
        {failed ? <TriangleAlert className="size-4 text-warning" aria-hidden="true" /> : <Sparkles className="size-4" aria-hidden="true" />}
        <div className="space-y-1">
          <p className="font-medium">{message}</p>
          {retrying && onCancel && <AiWaiting pending elapsed={elapsed} onCancel={onCancel} what="AI 판정" />}
          {defaultsAdded > 0 && !pendingState && (
            <p className="text-xs text-muted-foreground">AI 가 '다르다' 로 본 {defaultsAdded}건은 [관련 없음] 으로 미리 골랐습니다 — 바꿀 수 있습니다.</p>
          )}
          {coreKeywords && coreKeywords.length > 0 && (
            <p className="text-xs text-muted-foreground">겹친 키워드는 아이디어 핵심어만 셉니다: {coreKeywords.join(", ")}</p>
          )}
        </div>
      </div>
      {failed && !retrying && (
        <Button size="sm" variant="outline" onClick={onRetry}>
          <RefreshCw aria-hidden="true" />
          다시 시도
        </Button>
      )}
    </div>
  );
}
