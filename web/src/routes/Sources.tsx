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
      {q.data && q.data.sources.some((s) => s.notice) && (
        <div role="alert" className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100">
          <p className="font-medium">호출이 거부된 자료원이 있습니다</p>
          <ul className="mt-1 list-disc pl-5">
            {q.data.sources.filter((s) => s.notice).map((s) => (
              <li key={s.source}>
                {s.label}: {s.notice}
              </li>
            ))}
          </ul>
        </div>
      )}
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
                    {s.notice && (
                      <div className="mt-1">
                        <Badge variant="destructive">호출 거부</Badge> <span className="text-xs">{s.notice}</span>
                      </div>
                    )}
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
