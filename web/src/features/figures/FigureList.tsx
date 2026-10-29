import type { FigureSlot, FigureV2 } from "@/api/types";
import { sectionTitle } from "@/lib/sections";
import { FigureCard } from "./FigureCard";
import { FigureSlotCard } from "./FigureSlotCard";
import { DismissedRecommendations } from "./TechniqueCard";

export interface FigureListProps {
  runId: string;
  figures: FigureV2[] | undefined;
  section: string;
  baseVersion: number;
  disabled?: boolean;
  readOnly?: boolean;
  version?: number | null;
  onApplied: (version: number) => void;
  /** ADR 0045 — 이 섹션의 그림 자리(그리는 중·실패). 현재 버전에서만 넘긴다 */
  slots?: FigureSlot[];
}

/** 한 섹션의 그림 카드 목록. [필요 없음]으로 뺀 추천 그림은 아래에 접어 둔다(다시 넣기). 없으면 아무것도 그리지 않는다. */
export function FigureList({ runId, figures, section, baseVersion, disabled, readOnly, version, onApplied, slots = [] }: FigureListProps) {
  const all = (figures ?? []).filter((f) => f.section === section);
  const dismissed = all.filter((f) => f.recommendation?.status === "dismissed");
  const items = all.filter((f) => f.recommendation?.status !== "dismissed");
  const mine = slots.filter((s) => s.section === section);
  if (all.length === 0 && mine.length === 0) return null;
  return (
    <div className="space-y-2">
      {(items.length > 0 || mine.length > 0) && (
        <ul className="grid gap-3 md:grid-cols-2" aria-label={`${sectionTitle(section)} 그림 ${items.length + mine.length}장`}>
          {items.map((f) => (
            <li key={f.id} className="min-w-0">
              <FigureCard runId={runId} figure={f} baseVersion={baseVersion} disabled={disabled} readOnly={readOnly} version={version} onApplied={onApplied} />
            </li>
          ))}
          {mine.map((s) => (
            <li key={s.slot_id} className="min-w-0">
              <FigureSlotCard runId={runId} slot={s} baseVersion={baseVersion} disabled={disabled} onApplied={onApplied} />
            </li>
          ))}
        </ul>
      )}
      <DismissedRecommendations runId={runId} figures={dismissed} baseVersion={baseVersion} disabled={disabled} readOnly={readOnly} onApplied={onApplied} />
    </div>
  );
}
