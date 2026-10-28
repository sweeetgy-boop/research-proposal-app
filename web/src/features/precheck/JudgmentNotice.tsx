import { RefreshCw, Sparkles, TriangleAlert } from "lucide-react";
import type { JudgmentInfo } from "@/api/types";
import { Button } from "@/components/ui/button";

/** AI 같음 판정 안내 — 실패면 "AI 판정 실패 — 규칙 기준" + [다시 시도]. 빈 결과로 끝내지 않는다. */
export function JudgmentNotice({
  judgment,
  coreKeywords,
  onRetry,
  retrying,
}: {
  judgment: JudgmentInfo | undefined;
  coreKeywords?: string[];
  onRetry: () => void;
  retrying: boolean;
}) {
  if (!judgment) return null;
  const failed = judgment.retry_available;
  return (
    <div
      role="status"
      className={`flex flex-wrap items-start justify-between gap-2 rounded-md border p-3 text-sm ${failed ? "border-warning/60" : ""}`}
    >
      <div className="flex items-start gap-2">
        {failed ? <TriangleAlert className="size-4 text-warning" aria-hidden="true" /> : <Sparkles className="size-4" aria-hidden="true" />}
        <div>
          <p className="font-medium">{judgment.message}</p>
          {coreKeywords && coreKeywords.length > 0 && (
            <p className="text-xs text-muted-foreground">공유 키워드는 아이디어 핵심어만 셉니다: {coreKeywords.join(", ")}</p>
          )}
        </div>
      </div>
      {failed && (
        <Button size="sm" variant="outline" onClick={onRetry} disabled={retrying}>
          <RefreshCw className={retrying ? "animate-spin" : ""} aria-hidden="true" />
          {retrying ? "다시 판정 중…" : "다시 시도"}
        </Button>
      )}
    </div>
  );
}
