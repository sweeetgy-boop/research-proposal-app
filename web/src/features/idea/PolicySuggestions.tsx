import { useQuery } from "@tanstack/react-query";
import { BookMarked, RefreshCw } from "lucide-react";
import { fetchPolicySuggestions, formatPolicyQuote } from "@/api/policySuggestions";
import type { ProposalRequest } from "@/api/types";
import { Button } from "@/components/ui/button";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { UntrustedText } from "@/components/UntrustedText";

export const POLICY_UNAVAILABLE = "정책 근거 추천은 정책 자료 적재 뒤 열립니다.";

/** ① 정책 근거 추천 — 다른 레인의 엔드포인트. 제안자가 [추천 받기]를 누를 때 한 번 부르고, 404/405/503 이면 영역을 접고 한 줄 안내만.
 *  고른 문구는 제안자가 눌렀을 때만 정책 근거 칸 뒤에 덧붙는다(자동 반영 없음). */
export function PolicySuggestions({ request, onPick }: { request: ProposalRequest; onPick: (text: string) => void }) {
  const probe = useQuery({
    queryKey: ["policy-suggestions", request.current_state, request.root_cause, request.limitation, request.goal, request.title_hint],
    queryFn: () => fetchPolicySuggestions(request),
    staleTime: 5 * 60_000,
    retry: false,
    enabled: false, // 버튼으로만
  });
  const data = probe.data;
  if (data?.state === "unavailable") {
    return (
      <p className="text-xs text-muted-foreground" role="status">
        {POLICY_UNAVAILABLE}
      </p>
    );
  }
  return (
    <section aria-labelledby="policy-h" className="space-y-3 rounded-lg border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="policy-h" className="flex items-center gap-2 text-base font-semibold">
          <BookMarked className="size-4" aria-hidden="true" />
          정책 근거 추천
        </h2>
        <Button variant="outline" size="sm" onClick={() => probe.refetch()} disabled={probe.isFetching}>
          <RefreshCw className={probe.isFetching ? "animate-spin" : ""} aria-hidden="true" />
          {data ? "다시 받기" : "추천 받기"}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">정책 자료에서 찾은 문구입니다(수집 자료, 비신뢰). 고른 것만 정책 근거 칸 뒤에 덧붙습니다 — 자동으로 넣지 않습니다.</p>
      {probe.isFetching ? (
        <SkeletonBlock lines={2} />
      ) : data?.state === "error" ? (
        <ProblemBanner error={data.error} onRetry={() => probe.refetch()} />
      ) : data?.state === "ok" && data.items.length === 0 ? (
        <p className="text-sm text-muted-foreground">추천할 문구가 없습니다. 목표를 더 구체적으로 적으면 나아집니다.</p>
      ) : data?.state === "ok" ? (
        <ul className="space-y-2">
          {data.items.map((s, i) => (
            <li key={i} className="flex flex-wrap items-start justify-between gap-2 rounded-md border p-3 text-sm">
              <div className="min-w-0 flex-1">
                <UntrustedText as="p" text={s.quote} />
                <p className="mt-1 text-xs text-muted-foreground">
                  <UntrustedText text={s.document} />
                  {s.year ? ` · ${s.year}` : ""}
                  {s.page ? ` · p.${s.page}` : ""}
                  {s.url && (
                    <>
                      {" · "}
                      <a href={s.url} target="_blank" rel="noreferrer noopener" className="underline">
                        원문
                      </a>
                    </>
                  )}
                </p>
              </div>
              <Button size="sm" variant="secondary" onClick={() => onPick(formatPolicyQuote(s))}>
                정책 근거에 추가
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
