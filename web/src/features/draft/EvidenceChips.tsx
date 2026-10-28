import type { Citation } from "@/api/types";
import { DocRefList } from "@/components/DocRef";
import { docRef } from "@/lib/docRefs";

/** 문장 근거 → "제목 · 자료원 이름" 칩 (내부 번호 없음, ADR 0040). 누르면 onOpen(근거 패널), 없으면 요약·원문 창. */
export function EvidenceChips({ evidence, citations, onOpen }: { evidence: string[]; citations: Citation[]; onOpen?: () => void }) {
  if (evidence.length === 0) return null;
  const refs = evidence.map((id) => docRef(id, citations));
  return <DocRefList refs={refs} onOpen={onOpen ? () => onOpen() : undefined} />;
}
