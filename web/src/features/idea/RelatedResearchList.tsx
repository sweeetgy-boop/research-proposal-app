import { BookOpen, ExternalLink } from "lucide-react";
import type { RelatedResearch } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { UntrustedText } from "@/components/UntrustedText";
import { LiveBadge } from "@/features/live/LiveBadge";
import { MAX_REFERENCES, REFERENCE_LIMIT_NOTE } from "@/features/precheck/model";
import { RELATED_RESEARCH_HEADING_ID } from "./relatedResearchFocus";

const DOC_TYPE_LABELS: Record<string, string> = {
  paper: "논문",
  report: "보고서",
  internal_report: "보고서",
  patent: "특허",
};

/** ② "관련 연구" — 논문·보고서·특허 상위 n 건. 유사과제 판정이 아니라 참고 목록이라 배지는 "참고" 하나뿐이다 (ADR 0028).
 *  `onToggle` 이 있으면 행마다 [차별화에 참고] 체크(기본 해제, 최대 5건)를 둔다 — 고른 자료는 판정·차단에 쓰지 않고
 *  비교표·활용 제안·과제안 근거에만 쓴다 (ADR 0053). `onToggle` 없이 `selected` 만 주면 고른 행에 배지만 보인다(읽기 전용). */
export function RelatedResearchList({
  items,
  selected,
  onToggle,
}: {
  items: RelatedResearch[];
  /** [차별화에 참고] 로 고른 doc_id */
  selected?: readonly string[];
  onToggle?: (docId: string, on: boolean) => void;
}) {
  const picked = new Set(selected ?? []);
  const selectable = !!onToggle;
  const full = picked.size >= MAX_REFERENCES;
  return (
    <section id="related-research" className="space-y-3" aria-labelledby={RELATED_RESEARCH_HEADING_ID}>
      <div>
        <h2 id={RELATED_RESEARCH_HEADING_ID} tabIndex={-1} className="flex items-center gap-2 text-lg font-semibold focus-visible:outline-none">
          <BookOpen aria-hidden="true" className="size-5" />
          관련 연구 {items.length}건
        </h2>
        <p className="text-sm text-muted-foreground">
          논문·연구보고서·특허는 기수행 과제가 아니므로 유사과제 판정에 넣지 않습니다. 선행연구 참고용입니다.
          {selectable && items.length > 0
            ? ` [차별화에 참고] 로 고른 자료(최대 ${MAX_REFERENCES}건)는 비교표·활용 제안·차별화 과제안의 근거로만 씁니다. 고른 뒤 [선택 적용] 을 누르십시오.`
            : ""}
        </p>
      </div>
      {items.length === 0 ? (
        <p className="rounded-lg border bg-card px-3 py-4 text-sm text-muted-foreground">관련 연구가 없습니다.</p>
      ) : (
        <>
          <ul className="divide-y rounded-lg border">
            {items.map((r, i) => {
              const on = picked.has(r.doc_id);
              const boxId = `related-ref-${i}`;
              return (
                <li key={r.doc_id} className="flex flex-wrap items-start gap-x-3 gap-y-1 px-3 py-2 text-sm" data-testid="related-research-row">
                  <Badge variant="outline">참고</Badge>
                  {r.live && <LiveBadge />}
                  {!selectable && on && <Badge variant="secondary">차별화에 참고</Badge>}
                  <div className="min-w-0 flex-1">
                    <UntrustedText text={r.title} className="font-medium" />
                    <p className="text-xs text-muted-foreground">
                      {r.source_label}
                      {DOC_TYPE_LABELS[r.doc_type] ? ` · ${DOC_TYPE_LABELS[r.doc_type]}` : ""}
                      {r.year ? ` · ${r.year}` : ""}
                    </p>
                  </div>
                  {r.url ? (
                    <a href={r.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs underline underline-offset-2">
                      원문 <ExternalLink aria-hidden="true" className="size-3" />
                      <span className="sr-only">(새 창)</span>
                    </a>
                  ) : null}
                  {selectable && (
                    <div className="flex w-full items-center gap-2 sm:w-auto">
                      <Checkbox
                        id={boxId}
                        data-testid="reference-checkbox"
                        checked={on}
                        disabled={!on && full}
                        aria-describedby={!on && full ? "reference-limit-note" : undefined}
                        onChange={(e) => onToggle(r.doc_id, e.target.checked)}
                      />
                      <label htmlFor={boxId} className="cursor-pointer text-sm">
                        {"차별화에 참고 "}
                        <span className="sr-only">
                          {"— "}
                          <UntrustedText text={r.title} />
                        </span>
                      </label>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
          {selectable && (
            <p id="reference-limit-note" aria-live="polite" className="text-sm text-muted-foreground" data-testid="reference-limit-note">
              {full ? REFERENCE_LIMIT_NOTE : picked.size > 0 ? `참고로 고른 자료 ${picked.size}건 (최대 ${MAX_REFERENCES}건)` : ""}
            </p>
          )}
        </>
      )}
    </section>
  );
}
