import { Columns3 } from "lucide-react";
import type { ComparisonFlow } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ProblemBanner } from "@/components/ProblemBanner";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { UntrustedText } from "@/components/UntrustedText";
import { comparisonKindLabel, referenceRankLabel } from "@/lib/labels";
import { tierLabel } from "@/lib/tiers";
import { cn } from "@/lib/utils";

const EMPTY_CELLS = new Set(["정보 없음", "정보 없음(제목 기준)", "—"]);

/** 차별성 비교표 — [유사함] 으로 고른 과제 + ② 관련 연구에서 [차별화에 참고] 로 고른 자료(구분 '선행연구', ADR 0053).
 *  선행연구 열에는 "관련 순위 n/총수"(② 관련 연구 목록 안의 자리, 점수 숫자 없음). 넓은 화면은 표(칸 최소 폭, 가로 스크롤),
 *  좁은 화면은 과제별 카드. */
export function ComparisonView({
  data,
  loading,
  error,
  onRetry,
}: {
  data: ComparisonFlow | null | undefined;
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
}) {
  const header = (
    <h2 className="flex items-center gap-2 text-lg font-semibold">
      <Columns3 className="size-5" aria-hidden="true" />
      차별성 비교표
    </h2>
  );
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
  if (data.projects.length === 0) {
    return (
      <section className="space-y-2">
        {header}
        <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
          {data.empty_reason ?? "유사한 과제를 고르면 비교표가 만들어집니다"}
        </p>
      </section>
    );
  }
  const rows = [data.proposal, ...data.projects];
  const refCount = data.projects.filter((p) => p.kind === "reference").length;
  const simCount = data.projects.length - refCount;
  // 선행연구 열의 "관련 순위 n/총수" — ② 관련 연구 목록 밖·옛 서버면 표시 없음
  const relevanceNote = (r: (typeof rows)[number]) => {
    const label = r.kind === "reference" ? referenceRankLabel(r.relevance_rank, r.relevance_total) : null;
    return label ? (
      <span className="mt-1 block text-xs font-normal text-muted-foreground" data-testid="reference-relevance">
        {label}
      </span>
    ) : null;
  };
  // 선행연구 열이 섞였을 때만 열마다 구분을 보인다 (유사과제만이면 예전 모양 그대로)
  const kindBadge = (kind: string | undefined) =>
    refCount > 0 ? (
      <Badge variant={kind === "reference" ? "success" : "outline"} className="mb-1" data-testid="comparison-kind">
        {comparisonKindLabel(kind)}
      </Badge>
    ) : null;
  return (
    <section className="space-y-2">
      {header}
      <p className="text-sm text-muted-foreground">
        {refCount > 0
          ? `[유사함] 으로 고른 과제 ${simCount}건, 참고로 고른 선행연구 ${refCount}건과 제안 과제를 나란히 둡니다.`
          : `[유사함] 으로 고른 과제 ${data.projects.length}건과 제안 과제를 나란히 둡니다.`}{" "}
        {data.proposal_source === "draft" ? "제안 과제 칸은 초안에서 왔습니다. " : "제안 과제 칸은 입력·고른 과제안에서 왔습니다. "}
        {data.extraction_label} 양식에는 들어가지 않습니다.
      </p>
      {/* 넓은 화면: 표 */}
      <div className="relative hidden overflow-x-auto rounded-lg border md:block">
        <table className="w-full min-w-[64rem] table-fixed text-sm">
          <caption className="sr-only">차별성 비교표 — 과제별 다섯 관점</caption>
          <thead className="bg-muted/60 text-left">
            <tr>
              <th scope="col" className="w-48 p-2 font-semibold">과제</th>
              {data.aspects.map((a) => (
                <th key={a.key} scope="col" className="min-w-[10rem] p-2 font-semibold">
                  {a.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.doc_id ?? "proposal"} className={cn("border-t align-top", i === 0 && "bg-primary/5")}>
                <th scope="row" className="p-2 font-medium break-keep">
                  {i === 0 ? <Badge className="mb-1">제안 과제</Badge> : kindBadge(r.kind)}
                  <UntrustedText as="div" text={r.title} />
                  {i > 0 && r.tier && (
                    <span className="mt-1 block text-xs font-normal text-muted-foreground">{tierLabel({ tier: r.tier })}</span>
                  )}
                  {i > 0 && relevanceNote(r)}
                </th>
                {data.aspects.map((a) => {
                  const cell = r.cells[a.key] || "정보 없음";
                  return (
                    <td key={a.key} className={cn("p-2 break-keep", EMPTY_CELLS.has(cell) && "text-muted-foreground")}>
                      <UntrustedText text={cell} />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {/* 좁은 화면: 과제별 카드 */}
      <ul className="grid gap-3 md:hidden" aria-label="차별성 비교 — 과제별 카드">
        {rows.map((r, i) => (
          <li key={r.doc_id ?? "proposal"}>
            <Card className={i === 0 ? "border-primary" : undefined}>
              <CardHeader>
                <CardTitle className="text-base">
                  {i === 0 ? <Badge className="mr-2">제안 과제</Badge> : refCount > 0 ? <span className="mr-2">{kindBadge(r.kind)}</span> : null}
                  <UntrustedText text={r.title} />
                  {i > 0 && relevanceNote(r)}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <dl className="space-y-2 text-sm">
                  {data.aspects.map((a) => (
                    <div key={a.key}>
                      <dt className="font-medium">{a.label}</dt>
                      <dd className="text-muted-foreground">
                        <UntrustedText text={r.cells[a.key] || "정보 없음"} />
                      </dd>
                    </div>
                  ))}
                </dl>
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>
    </section>
  );
}
