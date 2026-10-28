import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface AiWaitingProps {
  pending: boolean;
  elapsed: number;
  onCancel: () => void;
  /** 무엇을 기다리는지 (예: "Argon 다시 쓰기") — 앞에 붙인다 */
  what?: string;
  className?: string;
}

/** AI 응답 대기 표시 — 시간 제한 없음. "응답 기다리는 중 · 경과 n초" + [취소] (취소하면 화면은 이전 상태). */
export function AiWaiting({ pending, elapsed, onCancel, what, className }: AiWaitingProps) {
  if (!pending) return null;
  return (
    <div role="status" aria-live="polite" className={cn("flex flex-wrap items-center gap-2 text-sm text-muted-foreground", className)}>
      <Loader2 className="size-4 animate-spin" aria-hidden />
      <span>
        {what ? `${what} — ` : ""}응답 기다리는 중 · 경과 {elapsed}초
      </span>
      <Button size="sm" variant="outline" onClick={onCancel}>
        취소
      </Button>
    </div>
  );
}

/** 취소 뒤 한 줄 안내 (화면은 그대로) */
export function AiCancelledNote({ show, className }: { show: boolean; className?: string }) {
  if (!show) return null;
  return <p className={cn("text-sm text-muted-foreground", className)}>취소했습니다. 화면은 이전 상태 그대로입니다.</p>;
}
