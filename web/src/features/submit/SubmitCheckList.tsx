import * as React from "react";
import { CheckCircle2, ChevronRight, XCircle } from "lucide-react";
import type { CheckAlertRow, SubmitCheckItem, SubmitCheckOut } from "@/api/types";
import { targetPath } from "./targets";
import { Badge } from "@/components/ui/badge";
import { UntrustedText } from "@/components/UntrustedText";
import { cn } from "@/lib/utils";
import { PROBLEM_LABELS, UNKNOWN_PROBLEM } from "@/lib/labels";
import { replaceDocIds } from "@/lib/docRefs";
import { sectionTitle } from "@/lib/sections";

/** 미해결 알림의 코드별 줄 — 설명(코드 아님)·건수·주의/오류 */
function AlertRows({ rows }: { rows: CheckAlertRow[] }) {
  if (rows.length === 0) return null;
  return (
    <ul className="mt-2 space-y-1 text-sm" aria-label="미해결 알림 종류">
      {rows.map((r) => (
        <li key={r.code} className="flex flex-wrap items-center gap-1.5">
          <Badge variant={r.severity === "error" ? "destructive" : "warning"}>{r.severity_label || (r.severity === "error" ? "오류" : "주의")}</Badge>
          <span>{r.label || PROBLEM_LABELS[r.code] || UNKNOWN_PROBLEM}</span>
          <span className="text-muted-foreground">{r.count}건</span>
        </li>
      ))}
    </ul>
  );
}

export function SubmitCheckList({
  check,
  runId,
  onGo,
  extra,
}: {
  check: SubmitCheckOut;
  runId: string;
  onGo: (path: string) => void;
  /** 항목 아래 동작(근거 일괄 승인·선택형 확정 등) — 이동 버튼 밖에 그린다 */
  extra?: (item: SubmitCheckItem) => React.ReactNode;
}) {
  return (
    <ul className="divide-y rounded-lg border" aria-label="제출 전 점검 항목">
      {check.items.map((it: SubmitCheckItem) => {
        const path = targetPath(runId, it.target);
        const rows = it.key === "unresolved_alerts" && Array.isArray(it.by_label) ? (it.by_label as CheckAlertRow[]) : [];
        const more = extra?.(it);
        const body = (
          <>
            {it.ok ? <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-success" aria-hidden="true" /> : <XCircle className="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden="true" />}
            <span className="min-w-0 flex-1">
              <span className="flex flex-wrap items-center gap-1.5">
                <span className="font-medium">{it.label}</span>
                <Badge variant={it.ok ? "success" : "destructive"}>{it.ok ? "통과" : "확인 필요"}</Badge>
                {it.count > 0 && <span className="text-xs text-muted-foreground">{it.count}건</span>}
              </span>
              {rows.length === 0 && <UntrustedText as="span" text={replaceDocIds(it.detail, [], sectionTitle)} className="block break-words text-sm text-muted-foreground" />}
              {it.target_label && <span className="block text-xs text-muted-foreground">→ {it.target_label}</span>}
            </span>
            {path && <ChevronRight className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />}
          </>
        );
        return (
          <li key={it.key}>
            {path ? (
              <button type="button" onClick={() => onGo(path)} className={cn("flex w-full items-start gap-3 p-3 text-left hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring")}>
                {body}
                <span className="sr-only"> — 이동</span>
              </button>
            ) : (
              <div className="flex items-start gap-3 p-3">{body}</div>
            )}
            {(rows.length > 0 || more) && (
              <div className="px-3 pb-3 pl-11">
                <AlertRows rows={rows} />
                {more}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
