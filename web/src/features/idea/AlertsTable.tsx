import type { OverlapAlert } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { UntrustedText } from "@/components/UntrustedText";
import { EmptyState } from "@/components/EmptyState";
import { ShieldCheck } from "lucide-react";
import { tierLabel } from "@/lib/tiers";
import { LiveBadge } from "@/features/live/LiveBadge";
import type { SeriesView } from "@/api/types";
import { seriesSources } from "@/features/precheck/model";
import { SeriesTitle } from "@/features/precheck/SeriesTitle";

/** 같은 연작 묶음 (ADR 0043) — 서버가 판이 둘 이상일 때만 싣는다 */
function seriesOf(a: OverlapAlert): SeriesView | null {
  return (a as { series?: SeriesView | null }).series ?? null;
}

function sourceText(a: OverlapAlert): string {
  const series = seriesOf(a);
  return series ? seriesSources(series) : ((a as { source_label?: string }).source_label ?? "");
}

export function AlertsTable({ alerts }: { alerts: OverlapAlert[] }) {
  if (alerts.length === 0) {
    return <EmptyState icon={ShieldCheck} title="유사과제가 없습니다" description="관련도·핵심 키워드 기준을 넘는 기존 과제가 없습니다." />;
  }
  return (
    <div className="relative overflow-x-auto rounded-lg border">
      <table className="w-full min-w-[40rem] text-sm">
        <caption className="sr-only">유사과제 목록</caption>
        <thead className="bg-muted/60 text-left text-muted-foreground">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">구분</th>
            <th scope="col" className="px-3 py-2 font-medium">과제·문서</th>
            <th scope="col" className="px-3 py-2 font-medium">관련도</th>
            <th scope="col" className="px-3 py-2 font-medium">공유 키워드</th>
            <th scope="col" className="px-3 py-2 font-medium">상태</th>
            <th scope="col" className="px-3 py-2 font-medium">판정</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((a) => (
            <tr key={a.doc_id} className="border-t align-top">
              <td className="px-3 py-2 whitespace-nowrap">{tierLabel(a)}</td>
              <td className="px-3 py-2">
                {seriesOf(a) ? (
                  <SeriesTitle series={seriesOf(a)!} id={`run-${a.doc_id.replace(/[^A-Za-z0-9_-]/g, "-")}`} />
                ) : (
                  <UntrustedText text={a.title} className="font-medium" />
                )}
                {a.live && <LiveBadge className="ml-2 align-middle" />}
                {sourceText(a) ? <p className="text-xs text-muted-foreground">{sourceText(a)}</p> : null}
              </td>
              <td className="px-3 py-2">{(a as { relevance_label?: string | null }).relevance_label ?? "—"}</td>
              <td className="px-3 py-2">
                <ul className="flex flex-wrap gap-1">
                  {a.keywords.map((k) => (
                    <li key={k}>
                      <Badge variant="secondary"><UntrustedText text={k} /></Badge>
                    </li>
                  ))}
                </ul>
              </td>
              <td className="px-3 py-2">{a.status_label ?? a.status ?? "—"}</td>
              <td className="px-3 py-2">
                {a.blocking ? <Badge variant="destructive">차단</Badge> : <Badge variant="warning">근접</Badge>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
