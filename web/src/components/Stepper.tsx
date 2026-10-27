import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export const FLOW_STEPS = [
  { n: 1, label: "아이디어 입력" },
  { n: 2, label: "유사과제 확인" },
  { n: 3, label: "초안 생성" },
  { n: 4, label: "직접 수정" },
  { n: 5, label: "최종 검토" },
  { n: 6, label: "최종 마무리" },
] as const;

const CIRCLED = ["①", "②", "③", "④", "⑤", "⑥"];

/** 전체 흐름 ①~⑥ 진행 표시. current 가 없으면 흐름 밖 화면(목록·검색). */
export function Stepper({ current, className }: { current: number | null; className?: string }) {
  return (
    <nav aria-label="작성 단계" className={cn("relative overflow-x-auto", className)}>
      <ol className="flex min-w-max items-center gap-1 text-xs sm:gap-2 sm:text-sm">
        {FLOW_STEPS.map((s, i) => {
          const state = current === null ? "idle" : s.n < current ? "done" : s.n === current ? "current" : "todo";
          return (
            <li key={s.n} className="flex items-center gap-1 sm:gap-2">
              <span
                aria-current={state === "current" ? "step" : undefined}
                className={cn(
                  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 sm:px-3 sm:py-1",
                  state === "current" && "border-primary bg-primary text-primary-foreground font-semibold",
                  state === "done" && "border-success text-success",
                  (state === "todo" || state === "idle") && "border-border text-muted-foreground",
                )}
              >
                {state === "done" ? (
                  <Check className="size-3.5" aria-hidden="true" />
                ) : (
                  <span aria-hidden="true">{CIRCLED[i]}</span>
                )}
                <span className="sr-only">{`${s.n}단계${state === "done" ? " 완료" : state === "current" ? " 진행 중" : ""}: `}</span>
                {s.label}
              </span>
              {i < FLOW_STEPS.length - 1 && <span aria-hidden="true" className="h-px w-2 bg-border sm:w-4" />}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
