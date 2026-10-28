import type { Figure } from "@/api/types";
import { sectionTitle } from "@/lib/sections";
import { FigureCard } from "./FigureCard";

export interface FigureListProps {
  runId: string;
  figures: Figure[] | undefined;
  section: string;
  baseVersion: number;
  disabled?: boolean;
  readOnly?: boolean;
  version?: number | null;
  onApplied: (version: number) => void;
}

/** 한 섹션의 그림 카드 목록. 없으면 아무것도 그리지 않는다. */
export function FigureList({ runId, figures, section, baseVersion, disabled, readOnly, version, onApplied }: FigureListProps) {
  const items = (figures ?? []).filter((f) => f.section === section);
  if (items.length === 0) return null;
  return (
    <ul className="grid gap-3 md:grid-cols-2" aria-label={`${sectionTitle(section)} 그림 ${items.length}장`}>
      {items.map((f) => (
        <li key={f.id} className="min-w-0">
          <FigureCard runId={runId} figure={f} baseVersion={baseVersion} disabled={disabled} readOnly={readOnly} version={version} onApplied={onApplied} />
        </li>
      ))}
    </ul>
  );
}
