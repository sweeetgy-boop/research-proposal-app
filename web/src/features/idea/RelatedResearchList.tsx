import { BookOpen, ExternalLink } from "lucide-react";
import type { RelatedResearch } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { UntrustedText } from "@/components/UntrustedText";

const DOC_TYPE_LABELS: Record<string, string> = {
  paper: "논문",
  report: "보고서",
  internal_report: "보고서",
  patent: "특허",
};

/** ② "관련 연구" — 논문·보고서·특허 상위 n 건. 유사과제 판정이 아니라 참고 목록이라 배지는 "참고" 하나뿐이다 (ADR 0028). */
export function RelatedResearchList({ items }: { items: RelatedResearch[] }) {
  return (
    <section className="space-y-3" aria-labelledby="related-research-heading">
      <div>
        <h2 id="related-research-heading" className="flex items-center gap-2 text-lg font-semibold">
          <BookOpen aria-hidden="true" className="size-5" />
          관련 연구 {items.length}건
        </h2>
        <p className="text-sm text-muted-foreground">
          논문·연구보고서·특허는 기수행 과제가 아니므로 유사과제 판정에 넣지 않습니다. 선행연구 참고용입니다.
        </p>
      </div>
      {items.length === 0 ? (
        <p className="rounded-lg border px-3 py-4 text-sm text-muted-foreground">관련 연구가 없습니다.</p>
      ) : (
        <ul className="divide-y rounded-lg border">
          {items.map((r) => (
            <li key={r.doc_id} className="flex flex-wrap items-start gap-x-3 gap-y-1 px-3 py-2 text-sm">
              <Badge variant="outline">참고</Badge>
              <div className="min-w-0 flex-1">
                <UntrustedText text={r.title} className="font-medium" />
                <p className="text-xs text-muted-foreground">
                  {r.source_label}
                  {DOC_TYPE_LABELS[r.doc_type] ? ` · ${DOC_TYPE_LABELS[r.doc_type]}` : ""}
                  {r.year ? ` · ${r.year}` : ""}
                  {` · 유사도 ${r.similarity.toFixed(3)}`}
                  {" · "}
                  {r.doc_id}
                </p>
              </div>
              {r.url ? (
                <a href={r.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs underline underline-offset-2">
                  원문 <ExternalLink aria-hidden="true" className="size-3" />
                  <span className="sr-only">(새 창)</span>
                </a>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
