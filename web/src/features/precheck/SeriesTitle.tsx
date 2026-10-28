import * as React from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { SeriesView } from "@/api/types";
import { Button } from "@/components/ui/button";
import { DocRef } from "@/components/DocRef";
import { UntrustedText } from "@/components/UntrustedText";

/** ② 같은 연작 한 줄 (ADR 0043) — "광역철도 수송수요 예측(연작 7건)" + [펼치기]/[접기].
 *  펼치면 연도별 목록(제목 · 자료원 이름), 누르면 근거 패널(요약 + 원문 링크). 내부 번호는 보이지 않는다. */
export function SeriesTitle({ series, id }: { series: SeriesView; id: string }) {
  const [open, setOpen] = React.useState(false);
  const listId = `series-${id}`;
  return (
    <div>
      <div className="flex flex-wrap items-center gap-1">
        <UntrustedText text={series.display} className="font-medium" />
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-7 px-2 text-xs"
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <ChevronDown className="size-3" aria-hidden="true" /> : <ChevronRight className="size-3" aria-hidden="true" />}
          {open ? "접기" : "펼치기"}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">제목이 연도·차수만 다른 같은 계열 과제 — 선택은 묶음 전체에 적용됩니다.</p>
      {open && (
        <ol id={listId} className="mt-1 space-y-1" aria-label={`${series.label} 연도별 목록`}>
          {series.members.map((m, i) => (
            <li key={`${m.doc_id}-${i}`} className="flex flex-wrap items-center gap-1 text-xs">
              <span className="w-12 shrink-0 tabular-nums text-muted-foreground">{m.year ?? "—"}</span>
              <DocRef
                compact
                docRef={{ doc_id: m.doc_id, title: m.title, source: m.source, source_label: m.source_label, url: m.url, summary: m.summary }}
              />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
