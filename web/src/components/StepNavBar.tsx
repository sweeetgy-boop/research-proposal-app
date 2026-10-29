import * as React from "react";
import { useNavigate } from "react-router";
import { ArrowLeft, ArrowRight, ListTodo } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

/** 막대의 한쪽 단추 — to(경로)·onClick·formId(그 폼 제출) 중 하나. reason 이 있으면 못 누르고 이유를 보인다. */
export interface StepNavAction {
  label: string;
  to?: string | null;
  onClick?: () => void;
  formId?: string;
  reason?: string | null;
  busy?: boolean;
}

// 남은 일 알림은 한 번만 (같은 화면·같은 단계) — 새로 고침 전까지 기억
const noticed = new Set<string>();

function setHeightVar(px: number) {
  document.documentElement.style.setProperty("--stepnav-h", `${Math.ceil(px)}px`);
}

/** 단계 화면 아래 이동 막대 (항목 22) — 왼쪽 [← 이전 단계], 가운데 남은 일 요약, 오른쪽 [다음: ○○ →].
 *  화면 아래에 붙고, 높이를 :root 의 --stepnav-h 로 알린다(본문·다른 sticky 막대가 그만큼 띄운다).
 *  남은 일은 막지 않는다 — 넘어갈 때 한 번 알림만 보인다. */
export function StepNavBar({
  prev,
  next,
  remaining = [],
  noticeKey,
  extra,
}: {
  prev?: StepNavAction | null;
  next?: StepNavAction | null;
  remaining?: string[];
  /** 남은 일 알림을 한 번만 보이게 하는 열쇠 (예: run 번호 + 단계) */
  noticeKey?: string;
  /** 가운데에 덧붙일 것 (예: 화면 고유 단추) */
  extra?: React.ReactNode;
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { toast } = useToast();
  const uid = React.useId();

  React.useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setHeightVar(el.getBoundingClientRect().height);
    if (typeof ResizeObserver === "undefined") return () => setHeightVar(0);
    const ro = new ResizeObserver(() => setHeightVar(el.getBoundingClientRect().height));
    ro.observe(el);
    return () => {
      ro.disconnect();
      setHeightVar(0);
    };
  }, []);

  const go = (a: StepNavAction, forward: boolean) => {
    if (forward && remaining.length > 0) {
      const key = noticeKey ?? remaining.join("|");
      if (!noticed.has(key)) {
        noticed.add(key);
        toast(`남은 일이 있습니다: ${remaining.join(" · ")} — 나중에 해도 됩니다.`);
      }
    }
    if (a.onClick) a.onClick();
    else if (a.to) navigate(a.to);
  };

  const side = (a: StepNavAction | null | undefined, forward: boolean) => {
    if (!a) return <span />;
    const blocked = !!a.reason || a.busy;
    const reasonId = `${uid}-${forward ? "n" : "p"}`;
    const content = forward ? (
      <>
        {a.label}
        <ArrowRight aria-hidden="true" />
      </>
    ) : (
      <>
        <ArrowLeft aria-hidden="true" />
        {a.label}
      </>
    );
    return (
      <div className={cn("flex min-w-0 flex-col gap-0.5", forward ? "items-end text-right" : "items-start")}>
        {a.formId && !blocked ? (
          <Button type="submit" form={a.formId} variant={forward ? "default" : "outline"} size="sm">
            {content}
          </Button>
        ) : (
          <Button
            type="button"
            variant={forward ? "default" : "outline"}
            size="sm"
            disabled={blocked}
            aria-disabled={blocked}
            aria-describedby={a.reason ? reasonId : undefined}
            onClick={() => go(a, forward)}
            data-testid={forward ? "stepnav-next" : "stepnav-prev"}
          >
            {content}
          </Button>
        )}
        {a.reason && (
          <span id={reasonId} role="status" className="max-w-56 text-xs text-muted-foreground">
            {a.reason}
          </span>
        )}
      </div>
    );
  };

  return (
    <div
      ref={ref}
      role="navigation"
      aria-label="단계 이동"
      data-testid="stepnav"
      className="fixed inset-x-0 bottom-0 z-30 border-t lg:left-52 bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/85"
    >
      <div className="mx-auto grid max-w-6xl grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 px-4 py-2">
        {side(prev, false)}
        <div className="min-w-0 text-center text-xs text-muted-foreground" aria-live="polite">
          {remaining.length > 0 ? (
            <p className="inline-flex max-w-full items-center gap-1" data-testid="stepnav-remaining">
              <ListTodo className="size-3.5 shrink-0" aria-hidden="true" />
              <span className="truncate" title={remaining.join(" · ")}>
                남은 일: {remaining.join(" · ")}
              </span>
            </p>
          ) : null}
          {extra}
        </div>
        {side(next, true)}
      </div>
    </div>
  );
}
