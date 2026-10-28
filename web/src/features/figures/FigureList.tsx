import type { FigureV2 } from "@/api/types";
import { sectionTitle } from "@/lib/sections";
import { FigureCard } from "./FigureCard";
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
}

/** 한 섹션의 그림 카드 목록. [필요 없음]으로 뺀 추천 그림은 아래에 접어 둔다(다시 넣기). 없으면 아무것도 그리지 않는다. */
export function FigureList({ runId, figures, section, baseVersion, disabled, readOnly, version, onApplied }: FigureListProps) {
  const all = (figures ?? []).filter((f) => f.section === section);
  const dismissed = all.filter((f) => f.recommendation?.status === "dismissed");
  const items = all.filter((f) => f.recommendation?.status !== "dismissed");
  if (all.length === 0) return null;
  return (
    <div className="space-y-2">
      {items.length > 0 && (
        <ul className="grid gap-3 md:grid-cols-2" aria-label={`${sectionTitle(section)} 그림 ${items.length}장`}>
          {items.map((f) => (
            <li key={f.id} className="min-w-0">
              <FigureCard runId={runId} figure={f} baseVersion={baseVersion} disabled={disabled} readOnly={readOnly} version={version} onApplied={onApplied} />
            </li>
          ))}
        </ul>
      )}
      <DismissedRecommendations runId={runId} figures={dismissed} baseVersion={baseVersion} disabled={disabled} readOnly={readOnly} onApplied={onApplied} />
    </div>
  );
}
