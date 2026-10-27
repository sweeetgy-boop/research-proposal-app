import * as React from "react";
import { useWindowVirtualizer } from "@tanstack/react-virtual";

/** 창 스크롤 기준 가상 목록 — 긴 초안·버전 목록. 행 높이는 실측(measureElement). */
export function VirtualList<T>({
  items,
  estimate = 72,
  renderRow,
  getKey,
  as = "ul",
  className,
  ariaLabel,
}: {
  items: T[];
  estimate?: number;
  renderRow: (item: T, index: number) => React.ReactNode;
  getKey: (item: T, index: number) => string;
  as?: "ul" | "ol" | "div";
  className?: string;
  ariaLabel?: string;
}) {
  const parentRef = React.useRef<HTMLDivElement>(null);
  const [offset, setOffset] = React.useState(0);
  React.useLayoutEffect(() => {
    setOffset(parentRef.current?.offsetTop ?? 0);
  }, []);
  const v = useWindowVirtualizer({
    count: items.length,
    estimateSize: () => estimate,
    overscan: 8,
    scrollMargin: offset,
    getItemKey: (i) => getKey(items[i] as T, i),
  });
  const Tag = as;
  const rows = v.getVirtualItems();
  return (
    <div ref={parentRef} className={className} style={{ height: v.getTotalSize(), position: "relative" }}>
      <Tag
        aria-label={ariaLabel}
        className="list-none p-0"
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: "100%",
          transform: `translateY(${(rows[0]?.start ?? 0) - v.options.scrollMargin}px)`,
        }}
      >
        {rows.map((row) => (
          <li key={row.key as string} data-index={row.index} ref={v.measureElement} className="list-none">
            {renderRow(items[row.index] as T, row.index)}
          </li>
        ))}
      </Tag>
    </div>
  );
}
