import * as React from "react";
import { ExternalLink, FileText } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { UntrustedText } from "@/components/UntrustedText";
import { LiveBadge } from "@/features/live/LiveBadge";
import { type DocRefData, refSource, refTitle } from "@/lib/docRefs";
import { cn } from "@/lib/utils";

/** 근거 패널(요약 + 원문 링크) — DocRef 를 눌렀을 때. 문장 근거 화면은 onOpen 으로 EvidencePanel 을 대신 연다. */
export function DocRefPanel({ docRef, open, onClose }: { docRef: DocRefData; open: boolean; onClose: () => void }) {
  return (
    <Dialog open={open} onClose={onClose} title={refTitle(docRef)} description={refSource(docRef)} className="w-[min(96vw,40rem)]">
      <div className="space-y-3 text-sm">
        <div className="flex flex-wrap items-center gap-1">
          <Badge variant="secondary">{refSource(docRef)}</Badge>
          {docRef.live && <LiveBadge />}
        </div>
        {docRef.summary ? (
          <blockquote className="max-h-60 overflow-y-auto rounded bg-muted/60 p-2">
            <UntrustedText as="p" text={docRef.summary} />
          </blockquote>
        ) : (
          <p className="text-muted-foreground">요약이 없습니다. 원문에서 확인하십시오.</p>
        )}
        {docRef.url ? (
          <a href={docRef.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 underline">
            원문 <ExternalLink className="size-3" aria-hidden="true" />
          </a>
        ) : (
          <p className="text-xs text-muted-foreground">원문 링크 없음 (사내 자료이거나 링크가 없는 자료)</p>
        )}
        <p className="text-xs text-muted-foreground">제목·요약은 수집 자료(비신뢰)입니다.</p>
      </div>
    </Dialog>
  );
}

/** 문서 하나 — "제목 · 자료원 이름". 내부 번호는 보이지 않는다. 누르면 근거 패널(onOpen 이 있으면 그것). */
export function DocRef({
  docRef,
  onOpen,
  className,
  compact,
}: {
  docRef: DocRefData;
  /** 문장 근거 화면: EvidencePanel 을 연다. 없으면 DocRefPanel */
  onOpen?: () => void;
  className?: string;
  /** 칩 모양 (작게) */
  compact?: boolean;
}) {
  const [open, setOpen] = React.useState(false);
  const title = refTitle(docRef);
  const source = refSource(docRef);
  return (
    <>
      <button
        type="button"
        onClick={() => (onOpen ? onOpen() : setOpen(true))}
        className={cn(
          "inline-flex max-w-full items-center gap-1 rounded border bg-muted/50 px-1.5 py-0.5 text-left text-xs text-muted-foreground hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring",
          !compact && "text-sm",
          className,
        )}
        aria-label={`${title} (${source}) 근거 보기`}
      >
        <FileText className="size-3 shrink-0" aria-hidden="true" />
        <span className="min-w-0 truncate whitespace-pre-wrap">{title}</span>
        <span className="shrink-0 text-[0.7rem] opacity-80">· {source}</span>
        {docRef.live && <LiveBadge className="ml-0.5" />}
      </button>
      {!onOpen && open && <DocRefPanel docRef={docRef} open={open} onClose={() => setOpen(false)} />}
    </>
  );
}

/** 여러 문서 칩 */
export function DocRefList({ refs, onOpen, label = "근거" }: { refs: DocRefData[]; onOpen?: (ref: DocRefData) => void; label?: string }) {
  if (refs.length === 0) return null;
  return (
    <ul className="mt-1 flex flex-wrap gap-1" aria-label={label}>
      {refs.map((r, i) => (
        <li key={`${r.id ?? r.doc_id ?? i}`} className="max-w-full">
          <DocRef docRef={r} compact onOpen={onOpen ? () => onOpen(r) : undefined} />
        </li>
      ))}
    </ul>
  );
}
