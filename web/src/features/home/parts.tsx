/** 홈 전용 임시 조각 — 레인 4 의 components/ui/eyebrow·status-chip·progress-bar 와 같은 모양(인터페이스 합의).
 *  레인 4 가 main 에 들어오면 이 파일을 지우고 그쪽을 import 한다. */
import type * as React from "react";
import { cn } from "@/lib/utils";

/** 작은 대문자 영어 라벨 (장식 — 읽는 순서에서 뺀다) */
export function Eyebrow({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <p aria-hidden="true" className={cn("text-xs font-semibold uppercase tracking-[0.14em] text-primary", className)}>
      {children}
    </p>
  );
}

const CHIP_LABELS = { writing: "작성 중", reviewing: "검토 중", done: "마무리 완료" } as const;

export function StatusChip({ status, children }: { status: keyof typeof CHIP_LABELS; children?: React.ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex items-center whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-semibold",
        status === "done" && "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-200",
        status === "reviewing" && "bg-amber-50 text-amber-800 dark:bg-amber-950/50 dark:text-amber-200",
        status === "writing" && "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-200",
      )}
    >
      {children ?? CHIP_LABELS[status]}
    </span>
  );
}

export function ProgressBar({ value, label }: { value: number; label?: string }) {
  const v = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={v}
      aria-label={label ?? "진행률"}
      className="h-1.5 w-full overflow-hidden rounded-full bg-indigo-100 dark:bg-indigo-950"
    >
      <div className="h-full rounded-full bg-primary" style={{ width: `${v}%` }} />
    </div>
  );
}
