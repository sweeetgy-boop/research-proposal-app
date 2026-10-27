import type { OverlapAlert } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { UntrustedText } from "@/components/UntrustedText";
import { EmptyState } from "@/components/EmptyState";
import { ShieldCheck } from "lucide-react";
import { tierLabel } from "@/lib/tiers";

export function AlertsTable({ alerts }: { alerts: OverlapAlert[] }) {
  if (alerts.length === 0) {
    return <EmptyState icon={ShieldCheck} title="유사과제가 없습니다" description="유사도·공유 키워드 기준을 넘는 기존 과제가 없습니다." />;
  }
  return (
    <div className="relative overflow-x-auto rounded-lg border">
      <table className="w-full min-w-[40rem] text-sm">
        <caption className="sr-only">유사과제 목록</caption>
        <thead className="bg-muted/60 text-left text-muted-foreground">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">구분</th>
            <th scope="col" className="px-3 py-2 font-medium">과제·문서</th>
            <th scope="col" className="px-3 py-2 font-medium">유사도</th>
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
                <UntrustedText text={a.title} className="font-medium" />
                <p className="text-xs text-muted-foreground">{a.doc_id}{a.basis ? ` · ${a.basis}` : ""}</p>
              </td>
              <td className="px-3 py-2 tabular-nums">{a.similarity.toFixed(3)}</td>
              <td className="px-3 py-2">
                <ul className="flex flex-wrap gap-1">
                  {a.keywords.map((k) => (
                    <li key={k}>
                      <Badge variant="secondary"><UntrustedText text={k} /></Badge>
                    </li>
                  ))}
                </ul>
              </td>
              <td className="px-3 py-2">{a.status ?? "—"}</td>
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
