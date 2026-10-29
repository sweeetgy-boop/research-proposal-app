import * as React from "react";
import { Link } from "react-router";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { FLOW_STEPS, type StepTarget } from "@/lib/runSteps";

const CIRCLED = ["①", "②", "③", "④", "⑤", "⑥"];

/** 전체 흐름 ①~⑥ 진행 표시. current 가 없으면 흐름 밖 화면(목록·검색).
 *  base·targets 를 주면(run 안) 각 단계가 그 화면으로 가는 링크가 되고, 아직 못 여는 단계는
 *  링크가 아니라 이유("초안 생성 후 열립니다")를 마우스·키보드 초점에 보여 준다. */
export function Stepper({
  current,
  className,
  base,
  targets,
}: {
  current: number | null;
  className?: string;
  base?: string;
  targets?: StepTarget[];
}) {
  const uid = React.useId();
  return (
    <nav aria-label="작성 단계" className={cn("relative overflow-x-auto", className)}>
      <ol className={cn("flex min-w-max items-center gap-1 text-xs sm:gap-2 sm:text-sm", base !== undefined && "pb-7")}>
        {FLOW_STEPS.map((s, i) => {
          const state = current === null ? "idle" : s.n < current ? "done" : s.n === current ? "current" : "todo";
          const target = targets?.find((t) => t.n === s.n);
          const pill = cn(
            "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-medium transition-colors sm:px-3 sm:py-1",
            state === "current" && "border-primary bg-primary text-primary-foreground font-semibold",
            state === "done" && "border-transparent bg-mint text-mint-foreground",
            (state === "todo" || state === "idle") && "border-border bg-card text-muted-foreground",
          );
          const body = (
            <>
              {state === "done" ? <Check className="size-3.5" aria-hidden="true" /> : <span aria-hidden="true">{CIRCLED[i]}</span>}
              <span className="sr-only">{`${s.n}단계${state === "done" ? " 완료" : state === "current" ? " 진행 중" : ""}: `}</span>
              {s.label}
              <span className="sr-only"> ({s.hint})</span>
            </>
          );
          const reasonId = `${uid}-r${s.n}`;
          let node: React.ReactNode;
          if (base !== undefined && target && target.to !== null) {
            node = (
              <Link
                to={target.to ? `${base}/${target.to}` : base}
                aria-current={state === "current" ? "step" : undefined}
                className={cn(pill, "hover:underline focus-visible:outline-2 focus-visible:outline-ring", state !== "current" && "hover:border-primary/50 hover:bg-primary-soft hover:text-primary-soft-foreground")}
              >
                {body}
              </Link>
            );
          } else if (base !== undefined && target) {
            node = (
              <span className="group relative">
                <span
                  role="link"
                  aria-disabled="true"
                  tabIndex={0}
                  aria-describedby={reasonId}
                  title={target.reason ?? undefined}
                  className={cn(pill, "cursor-not-allowed opacity-60 focus-visible:outline-2 focus-visible:outline-ring")}
                >
                  {body}
                </span>
                <span
                  id={reasonId}
                  role="tooltip"
                  className="pointer-events-none absolute left-0 top-full z-10 mt-1 hidden whitespace-nowrap rounded-md border bg-card px-2 py-0.5 text-xs text-card-foreground shadow-pop group-hover:block group-focus-within:block"
                >
                  {target.reason}
                </span>
              </span>
            );
          } else {
            node = (
              <span aria-current={state === "current" ? "step" : undefined} className={pill}>
                {body}
              </span>
            );
          }
          return (
            <li key={s.n} className="flex items-center gap-1 sm:gap-2">
              {node}
              {i < FLOW_STEPS.length - 1 && <span aria-hidden="true" className="h-px w-2 bg-border sm:w-4" />}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
