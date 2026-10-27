import type { Citation } from "@/api/types";

/** 문장 근거 id → 인용 문서 제목(비신뢰) 칩. */
export function EvidenceChips({ evidence, citations }: { evidence: string[]; citations: Citation[] }) {
  if (evidence.length === 0) return null;
  const byId = new Map(citations.map((c) => [c.id, c]));
  return (
    <ul className="mt-1 flex flex-wrap gap-1" aria-label="근거">
      {evidence.map((id) => {
        const c = byId.get(id);
        return (
          <li key={id} className="rounded border bg-muted/50 px-1.5 py-0.5 text-xs text-muted-foreground" title={id}>
            {c?.title ? <span className="whitespace-pre-wrap">{c.title}</span> : id}
          </li>
        );
      })}
    </ul>
  );
}
