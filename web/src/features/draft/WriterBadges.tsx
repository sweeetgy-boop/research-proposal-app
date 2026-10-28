import type { FallbackSection, SectionWriter } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { localWriterNote } from "@/lib/writer";

/** 섹션 머리의 작성자 배지.
 *  - "로컬 작성"([3] Argon 우선 작성): Argon 실패 뒤 로컬 모델이 쓴 섹션 (local_sections + writers[key].reason)
 *  - "대체 작성"(ADR 0027, 옛 run): 로컬 2회 실패 뒤 외부 LLM 이 쓴 섹션 (fallback_sections) */
export function WriterBadges({ local, writer, fallback }: { local?: boolean; writer?: SectionWriter; fallback?: FallbackSection }) {
  if (!local && !fallback) return null;
  const note = localWriterNote(writer);
  return (
    <>
      {local && (
        <>
          <Badge variant="secondary" title={note}>
            로컬 작성
          </Badge>
          <span className="sr-only">({note})</span>
        </>
      )}
      {fallback && (
        <Badge variant="secondary" title={`로컬 모델 실패(${fallback.reason}) 뒤 ${fallback.provider}/${fallback.model} 이 작성`}>
          대체 작성
        </Badge>
      )}
    </>
  );
}
