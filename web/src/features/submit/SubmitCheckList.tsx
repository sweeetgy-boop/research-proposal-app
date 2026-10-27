import { CheckCircle2, ChevronRight, XCircle } from "lucide-react";
import type { SubmitCheckItem, SubmitCheckOut } from "@/api/types";
import { targetPath } from "./targets";
import { Badge } from "@/components/ui/badge";
import { UntrustedText } from "@/components/UntrustedText";
import { cn } from "@/lib/utils";

export function SubmitCheckList({ check, runId, onGo }: { check: SubmitCheckOut; runId: string; onGo: (path: string) => void }) {
  return (
    <ul className="divide-y rounded-lg border" aria-label="제출 전 점검 항목">
      {check.items.map((it: SubmitCheckItem) => {
        const path = targetPath(runId, it.target);
        const body = (
          <>
            {it.ok ? <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-success" aria-hidden="true" /> : <XCircle className="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden="true" />}
            <span className="min-w-0 flex-1">
              <span className="flex flex-wrap items-center gap-1.5">
                <span className="font-medium">{it.label}</span>
                <Badge variant={it.ok ? "success" : "destructive"}>{it.ok ? "통과" : "확인 필요"}</Badge>
                {it.count > 0 && <span className="text-xs text-muted-foreground">{it.count}건</span>}
              </span>
              <UntrustedText as="span" text={it.detail} className="block text-sm text-muted-foreground" />
              {it.target_label && <span className="block text-xs text-muted-foreground">→ {it.target_label}</span>}
            </span>
            {path && <ChevronRight className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />}
          </>
        );
        return (
          <li key={it.key}>
            {path ? (
              <button type="button" onClick={() => onGo(path)} className={cn("flex w-full items-start gap-3 p-3 text-left hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring")} aria-label={`${it.label}: ${it.ok ? "통과" : "확인 필요"} — 이동`}>
                {body}
              </button>
            ) : (
              <div className="flex items-start gap-3 p-3">{body}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
