import { Columns3 } from "lucide-react";
import type { ComparisonOut } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { UntrustedText } from "@/components/UntrustedText";
import { cn } from "@/lib/utils";
import { tierLabel } from "@/lib/tiers";

export const TITLE_ONLY = "정보 없음(제목 기준)";

export interface ComparisonTableProps {
  data: ComparisonOut["comparison"] | null | undefined;
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  /** doc_id → 추천 카드 번호 (있으면 과제 행에서 카드로 이동) */
  recommendationFor?: Map<string, number>;
  /** 503 — 기능 꺼짐 */
  unavailable?: boolean;
}

/** U4 차별성 비교표 — 행: 제안 과제 + 유사과제 상위 5건, 열: 5 관점. 기존 과제 칸은 수집 자료(비신뢰). 양식 밖. */
export function ComparisonTable({ data, loading, error, onRetry, recommendationFor, unavailable }: ComparisonTableProps) {
  const header = (
    <h2 className="flex items-center gap-2 text-lg font-semibold">
      <Columns3 className="size-5" aria-hidden="true" />
      차별성 비교표
    </h2>
  );
  if (unavailable) {
    return (
      <section className="space-y-2">
        {header}
        <p className="text-sm text-muted-foreground">비교표가 꺼져 있습니다 (usability.yaml comparison).</p>
      </section>
    );
  }
  if (loading) {
    return (
      <section className="space-y-2" aria-busy="true">
        {header}
        <SkeletonBlock lines={4} />
      </section>
    );
  }
  if (error) {
    return (
      <section className="space-y-2">
        {header}
        <ProblemBanner error={error} onRetry={onRetry} />
      </section>
    );
  }
  if (!data) return null;
  const rows = [data.proposal, ...data.projects.slice(0, 5)];
  return (
    <section className="space-y-2">
      {header}
      <p className="text-sm text-muted-foreground">
        제안 과제와 유사과제 상위 {data.projects.length}건을 다섯 관점으로 나란히 둡니다. 기존 과제 칸은 요약·초록에서 뽑은 문장이며, 제목만 있는 과제는 "{TITLE_ONLY}" 으로 둡니다. 양식에는 들어가지 않습니다.
      </p>
      <div className="relative overflow-x-auto rounded-lg border">
        <table className="w-full min-w-[56rem] text-sm">
          <caption className="sr-only">차별성 비교표 — 과제별 다섯 관점</caption>
          <thead className="bg-muted/60 text-left">
            <tr>
              <th scope="col" className="p-2 font-semibold">과제</th>
              {data.aspects.map((a) => (
                <th key={a.key} scope="col" className="p-2 font-semibold">
                  {a.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const isProposal = i === 0;
              const rec = r.doc_id ? recommendationFor?.get(r.doc_id) : undefined;
              return (
                <tr key={r.doc_id ?? "proposal"} className={cn("border-t align-top", isProposal && "bg-primary/5")}>
                  <th scope="row" className="min-w-40 p-2 font-medium">
                    {isProposal ? (
                      <>
                        <Badge className="mb-1">제안 과제</Badge>
                        <UntrustedText as="div" text={r.title} />
                      </>
                    ) : (
                      <>
                        <UntrustedText as="div" text={r.title} />
                        <div className="mt-1 flex flex-wrap gap-1 text-xs font-normal text-muted-foreground">
                          {r.tier && <Badge variant="outline">{tierLabel({ tier: r.tier })}</Badge>}
                          {r.similarity !== null && <span>유사도 {r.similarity.toFixed(2)}</span>}
                          {r.blocking && <Badge variant="destructive">차단</Badge>}
                          {r.title_only && <Badge variant="secondary">제목만</Badge>}
                        </div>
                        {rec !== undefined && (
                          <a href={`#rec-${rec}`} className="mt-1 inline-block text-xs underline">
                            추천 {rec + 1}번 카드 보기
                          </a>
                        )}
                      </>
                    )}
                  </th>
                  {data.aspects.map((a) => {
                    const cell = r.title_only && !isProposal ? TITLE_ONLY : r.cells[a.key] || "정보 없음";
                    const empty = cell === TITLE_ONLY || cell === "정보 없음";
                    return (
                      <td key={a.key} className={cn("p-2", empty && "text-muted-foreground")}>
                        <UntrustedText text={cell} />
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
