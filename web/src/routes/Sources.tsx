import { useSources } from "@/api/hooks";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { Badge } from "@/components/ui/badge";

export default function Sources() {
  const q = useSources();
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">자료원 상태</h1>
      <p className="text-sm text-muted-foreground">자료원별 적재 건수와 마지막 적재일. 야간 배치(02:30)가 갱신합니다.</p>
      {q.isPending && <SkeletonBlock lines={7} />}
      <ProblemBanner error={q.error} onRetry={() => q.refetch()} />
      {q.data && (
        <div className="relative overflow-x-auto rounded-lg border">
          <table className="w-full min-w-[28rem] text-sm">
            <caption className="sr-only">자료원별 적재 현황</caption>
            <thead className="bg-muted/60 text-left text-muted-foreground">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">자료원</th>
                <th scope="col" className="px-3 py-2 font-medium">건수</th>
                <th scope="col" className="px-3 py-2 font-medium">마지막 적재</th>
              </tr>
            </thead>
            <tbody>
              {q.data.sources.map((s) => (
                <tr key={s.source} className="border-t">
                  <td className="px-3 py-2">
                    {s.label} <span className="font-mono text-xs text-muted-foreground">{s.source}</span>
                  </td>
                  <td className="px-3 py-2 tabular-nums">{s.count.toLocaleString("ko-KR")}</td>
                  <td className="px-3 py-2">{s.last_ingested ?? <Badge variant="outline">없음</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
