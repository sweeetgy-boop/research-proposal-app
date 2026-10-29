import * as React from "react";
import { cn } from "@/lib/utils";

/** 제안서 상태 칩 — 작성 중(연보라) · 검토 중(살구) · 마무리 완료(민트). */
export type StudioStatus = "writing" | "reviewing" | "done";

export const STATUS_CHIP_LABELS: Record<StudioStatus, string> = {
  writing: "작성 중",
  reviewing: "검토 중",
  done: "마무리 완료",
};

const TONE: Record<StudioStatus, string> = {
  writing: "bg-primary-soft text-primary-soft-foreground",
  reviewing: "bg-apricot text-apricot-foreground",
  done: "bg-mint text-mint-foreground",
};

export interface StatusChipProps extends Omit<React.HTMLAttributes<HTMLSpanElement>, "children"> {
  status: StudioStatus;
  /** 기본 문구 대신 쓸 글자(선택) */
  children?: React.ReactNode;
}

export function StatusChip({ status, children, className, ...props }: StatusChipProps) {
  return (
    <span
      data-status={status}
      className={cn(
        "inline-flex items-center whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-semibold",
        TONE[status],
        className,
      )}
      {...props}
    >
      {children ?? STATUS_CHIP_LABELS[status]}
    </span>
  );
}
