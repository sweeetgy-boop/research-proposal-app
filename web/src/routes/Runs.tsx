import { Link } from "react-router";
import { ListOrdered } from "lucide-react";
import { useRuns } from "@/api/hooks";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { EmptyState } from "@/components/EmptyState";
import { statusLabel } from "@/lib/sections";
import { formatDate } from "@/lib/utils";

export default function Runs() {
  const q = useRuns();
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h1 className="text-2xl font-bold tracking-tight">run 목록</h1>
        <Link to="/new" className={buttonVariants()}>
          새 제안서
        </Link>
      </div>
      {q.isPending && <SkeletonBlock lines={5} />}
      <ProblemBanner error={q.error} onRetry={() => q.refetch()} />
      {q.data && q.data.runs.length === 0 && (
        <EmptyState icon={ListOrdered} title="아직 run 이 없습니다" description="새 제안서에서 아이디어를 입력하면 여기에 쌓입니다." />
      )}
      {q.data && q.data.runs.length > 0 && (
        <div className="relative overflow-x-auto rounded-lg border">
          <table className="w-full min-w-[40rem] text-sm">
            <caption className="sr-only">run 목록 (최근 순)</caption>
            <thead className="bg-muted/60 text-left text-muted-foreground">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">과제 제목</th>
                <th scope="col" className="px-3 py-2 font-medium">상태</th>
                <th scope="col" className="px-3 py-2 font-medium">버전</th>
                <th scope="col" className="px-3 py-2 font-medium">진행</th>
                <th scope="col" className="px-3 py-2 font-medium">만든 때</th>
                <th scope="col" className="px-3 py-2 font-medium">갱신</th>
              </tr>
            </thead>
            <tbody>
              {q.data.runs.map((r) => (
                <tr key={r.run_id} className="border-t">
                  <td className="max-w-[28rem] px-3 py-2">
                    <Link
                      to={`/runs/${r.run_id}`}
                      title={r.title || undefined}
                      className="line-clamp-2 break-words font-medium text-primary underline-offset-2 hover:underline"
                    >
                      {r.title?.trim() || "제목 미정"}
                    </Link>
                    <span className="block font-mono text-xs text-muted-foreground">{r.run_id}</span>
                    {r.legacy && <Badge variant="outline" className="mt-1">옛 run</Badge>}
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant="secondary">{statusLabel(r.status)}</Badge>
                    {r.flow.stale && <span className="ml-2 text-xs text-warning">수정 {r.flow.stale_edits}건</span>}
                  </td>
                  <td className="px-3 py-2 tabular-nums">v{r.draft_version}</td>
                  <td className="px-3 py-2 tabular-nums">
                    {r.progress[0]}/{r.progress[1]}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">{formatDate(r.created_at)}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{formatDate(r.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
