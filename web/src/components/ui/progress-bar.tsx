import { cn } from "@/lib/utils";

/** 얇은 진행률 막대 — 위에 작은 % 숫자, 아래 남보라 막대. role=progressbar(이름은 label, 없으면 "진행률"). */
export interface ProgressBarProps {
  /** 0~100 (범위 밖은 잘라 낸다) */
  value: number;
  /** 화면 읽기 프로그램용 이름(예: "레일 점검 제안서 진행률") */
  label?: string;
  /** % 숫자 표시(기본 켬) */
  showValue?: boolean;
  className?: string;
}

export function ProgressBar({ value, label, showValue = true, className }: ProgressBarProps) {
  const pct = Math.round(Math.min(100, Math.max(0, Number.isFinite(value) ? value : 0)));
  return (
    <div className={cn("flex min-w-16 flex-col gap-1", className)}>
      {showValue && (
        <span aria-hidden="true" className="text-xs font-medium tabular-nums text-muted-foreground">
          {pct}%
        </span>
      )}
      <div
        role="progressbar"
        aria-label={label ?? "진행률"}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-valuetext={`${pct}%`}
        className="h-1.5 w-full overflow-hidden rounded-full bg-primary-soft"
      >
        <div className="h-full rounded-full bg-primary transition-[width] duration-300" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
