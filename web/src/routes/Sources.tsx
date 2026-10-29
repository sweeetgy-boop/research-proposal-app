/** 자료 현황 — 자료원별 적재 건수·마지막 적재일·호출 거부 안내 (2026-10-29 [UI] 레인 3 새 모양, 같은 데이터).
 *  자료원 키(영어 코드)는 보이지 않는다 — 한국어 이름만. */
import { Database, ShieldAlert, Library } from "lucide-react";
import { Link } from "react-router";
import { useSources } from "@/api/hooks";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { Badge } from "@/components/ui/badge";
import { Eyebrow } from "@/components/ui/eyebrow";

function Stat({ icon: Icon, label, value, tone }: { icon: typeof Database; label: string; value: string; tone: string }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border bg-card p-4 shadow-card">
      <span className={`grid size-10 shrink-0 place-items-center rounded-lg ${tone}`}>
        <Icon className="size-5" aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <p className="text-sm text-muted-foreground">{label}</p>
        <p className="text-2xl font-bold tabular-nums leading-tight">{value}</p>
      </div>
    </div>
  );
}

export default function Sources() {
  const q = useSources();
  const rows = q.data?.sources ?? [];
  const total = rows.reduce((n, s) => n + s.count, 0);
  const loaded = rows.filter((s) => s.count > 0).length;
  const blocked = rows.filter((s) => s.notice);
  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <Eyebrow>Sources</Eyebrow>
        <h1 className="text-2xl font-bold tracking-tight">자료 현황</h1>
        <p className="text-sm text-muted-foreground">
          자료원별 적재 건수와 마지막 적재일입니다. 야간 배치(02:30)가 갱신합니다. 자료는{" "}
          <Link to="/search" className="text-primary underline-offset-2 hover:underline">
            자료 검색
          </Link>
          이나 위쪽 통합 검색에서 찾습니다.
        </p>
      </header>
      {blocked.length > 0 && (
        <div role="alert" className="rounded-xl bg-apricot p-4 text-sm text-apricot-foreground">
          <p className="flex items-center gap-1.5 font-semibold">
            <ShieldAlert className="size-4" aria-hidden="true" />
            호출이 거부된 자료원이 있습니다
          </p>
          <ul className="mt-1 list-disc pl-6">
            {blocked.map((s) => (
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
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <Stat icon={Library} label="전체 자료" value={`${total.toLocaleString("ko-KR")}건`} tone="bg-primary-soft text-primary-soft-foreground" />
            <Stat icon={Database} label="자료가 있는 자료원" value={`${loaded} / ${rows.length}`} tone="bg-mint text-mint-foreground" />
            <Stat icon={ShieldAlert} label="호출이 거부된 자료원" value={`${blocked.length}곳`} tone="bg-apricot text-apricot-foreground" />
          </div>
          <div className="relative overflow-x-auto rounded-xl border bg-card shadow-card">
            <table className="w-full min-w-[28rem] text-sm">
              <caption className="sr-only">자료원별 적재 현황</caption>
              <thead className="border-b text-left text-xs text-muted-foreground">
                <tr>
                  <th scope="col" className="px-4 py-3 font-medium">
                    자료원
                  </th>
                  <th scope="col" className="px-4 py-3 text-right font-medium">
                    건수
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    마지막 적재
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {rows.map((s) => (
                  <tr key={s.source}>
                    <td className="px-4 py-3">
                      <span className="font-medium">{s.label}</span>
                      {s.notice && (
                        <div className="mt-1">
                          <Badge variant="destructive">호출 거부</Badge> <span className="text-xs">{s.notice}</span>
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{s.count.toLocaleString("ko-KR")}</td>
                    <td className="px-4 py-3">{s.last_ingested ?? <Badge variant="outline">없음</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
