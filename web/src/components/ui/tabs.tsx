import * as React from "react";
import { cn } from "@/lib/utils";

/** 단순 탭(밑줄형) — role=tablist, 화살표 키 이동, aria-selected. 선택 탭은 남보라 글자 + 밑줄. */
export interface TabItem {
  id: string;
  label: string;
  /** 탭 이름 옆 작은 건수(선택) — 화면 읽기 프로그램에는 "label count" 로 읽힌다 */
  count?: number;
}

export function Tabs({
  items,
  value,
  onChange,
  label,
  className,
}: {
  items: TabItem[];
  value: string;
  onChange: (id: string) => void;
  label: string;
  className?: string;
}) {
  const refs = React.useRef<(HTMLButtonElement | null)[]>([]);
  const onKey = (e: React.KeyboardEvent, i: number) => {
    const n = items.length;
    let next = -1;
    if (e.key === "ArrowRight") next = (i + 1) % n;
    else if (e.key === "ArrowLeft") next = (i - 1 + n) % n;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = n - 1;
    if (next >= 0) {
      e.preventDefault();
      const item = items[next];
      if (item) {
        onChange(item.id);
        refs.current[next]?.focus();
      }
    }
  };
  return (
    <div role="tablist" aria-label={label} className={cn("relative flex gap-5 overflow-x-auto border-b", className)}>
      {items.map((t, i) => {
        const selected = t.id === value;
        return (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[i] = el;
            }}
            role="tab"
            type="button"
            id={`tab-${t.id}`}
            aria-selected={selected}
            aria-controls={`panel-${t.id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(t.id)}
            onKeyDown={(e) => onKey(e, i)}
            className={cn(
              "-mb-px inline-flex items-center gap-1.5 whitespace-nowrap border-b-2 px-0.5 py-2.5 text-sm font-semibold transition-colors",
              selected
                ? "border-primary text-primary-soft-foreground"
                : "border-transparent text-muted-foreground hover:border-border hover:text-foreground",
            )}
          >
            {t.label}
            {t.count !== undefined && (
              <>
                {" "}
                <span className="text-xs font-medium tabular-nums">{t.count}</span>
              </>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function TabPanel({ id, active, children, className }: { id: string; active: boolean; children: React.ReactNode; className?: string }) {
  if (!active) return null;
  return (
    <div role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`} tabIndex={0} className={cn("pt-4", className)}>
      {children}
    </div>
  );
}
