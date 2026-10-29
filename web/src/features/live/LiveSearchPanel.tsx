import { Radar } from "lucide-react";
import type { LiveSearch } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { UntrustedText } from "@/components/UntrustedText";
import {
  LIVE_SEARCH_STATUS_VARIANT,
  LIVE_SOURCE_STATUS_VARIANT,
  liveSearchStatusLabel,
  liveSourceLabel,
  liveSourceStatusLabel,
} from "@/lib/live";

function KeywordRow({ label, words }: { label: string; words: string[] }) {
  return (
    <div className="flex flex-wrap items-baseline gap-1">
      <dt className="w-10 shrink-0 text-muted-foreground">{label}</dt>
      <dd className="flex min-w-0 flex-1 flex-wrap gap-1">
        {words.length === 0 ? (
          <span className="text-muted-foreground">없음</span>
        ) : (
          words.map((w) => (
            <Badge key={w} variant="outline" className="whitespace-normal">
              <UntrustedText text={w} />
            </Badge>
          ))
        )}
      </dd>
    </div>
  );
}

/** [4] ② 실시간 검색 — 자료원별 상태(결과 수·상태·걸린 시간)·안내(NTIS IP 미등록 등)·검색어.
 *  안내 문구와 검색어는 서버·외부 API 에서 온 텍스트라 UntrustedText 로만 그린다. */
export function LiveSearchPanel({ live }: { live: LiveSearch }) {
  const pending = live.status === "pending";
  const notices = live.sources.filter((s) => s.notice);
  const ko = live.keywords?.ko ?? [];
  const en = live.keywords?.en ?? [];
  return (
    <section className="space-y-3" aria-labelledby="live-search-heading" aria-busy={pending || undefined}>
      <div>
        <h2 id="live-search-heading" className="flex flex-wrap items-center gap-2 text-lg font-semibold">
          <Radar aria-hidden="true" className="size-5" />
          실시간 검색
          <Badge variant={LIVE_SEARCH_STATUS_VARIANT[live.status] ?? "outline"}>
            <span className="sr-only">상태: </span>
            {liveSearchStatusLabel(live.status)}
          </Badge>
        </h2>
        <p className="text-sm text-muted-foreground">
          저장된 자료와 별도로 이번 입력의 검색어로 외부 자료원을 바로 조회했습니다. 여기서 찾은 항목에는 &lsquo;실시간 검색&rsquo; 표시가 붙습니다.
        </p>
      </div>

      <p role="status" aria-live="polite" className="text-sm">
        {pending ? "실시간 검색 중…" : live.status === "off" ? "실시간 검색이 꺼져 있어 저장된 자료만 확인했습니다." : ""}
      </p>

      {live.sources.length > 0 && (
        <div className="relative overflow-x-auto rounded-lg border">
          <table className="w-full min-w-[28rem] text-sm">
            <caption className="px-3 py-2 text-left text-sm font-semibold">자료원별 상태</caption>
            <thead className="bg-muted text-left text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">자료원</th>
                <th scope="col" className="px-3 py-2 font-medium">결과 수</th>
                <th scope="col" className="px-3 py-2 font-medium">상태</th>
                <th scope="col" className="px-3 py-2 font-medium">걸린 시간</th>
              </tr>
            </thead>
            <tbody>
              {live.sources.map((s) => (
                <tr key={s.source} className="border-t">
                  <th scope="row" className="px-3 py-2 text-left font-medium">{liveSourceLabel(s.source)}</th>
                  <td className="px-3 py-2 tabular-nums">{s.status === "off" ? "—" : `${s.count}건`}</td>
                  <td className="px-3 py-2">
                    <Badge variant={LIVE_SOURCE_STATUS_VARIANT[s.status] ?? "outline"}>{liveSourceStatusLabel(s.status)}</Badge>
                  </td>
                  <td className="px-3 py-2 tabular-nums">{s.status === "off" ? "—" : `${s.seconds.toFixed(1)}초`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {notices.length > 0 && (
        <ul className="space-y-1 text-sm" aria-label="자료원 안내">
          {notices.map((s) => (
            <li key={s.source} className="rounded-md border border-warning/30 bg-apricot px-3 py-2">
              <span className="font-medium">{liveSourceLabel(s.source)}: </span>
              <UntrustedText text={s.notice} />
            </li>
          ))}
        </ul>
      )}

      {(ko.length > 0 || en.length > 0) && (
        <details className="rounded-lg border bg-card px-3 py-2 text-sm">
          <summary className="cursor-pointer font-medium">검색어</summary>
          <dl className="mt-2 space-y-1">
            <KeywordRow label="국문" words={ko} />
            <KeywordRow label="영문" words={en} />
          </dl>
        </details>
      )}
    </section>
  );
}
