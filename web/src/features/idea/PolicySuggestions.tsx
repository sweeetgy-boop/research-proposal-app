import { BookMarked, ExternalLink, RefreshCw } from "lucide-react";
import { fetchPolicySuggestions, formatPolicyQuote, type PolicyProbe } from "@/api/policySuggestions";
import type { ProposalRequest } from "@/api/types";
import { Button } from "@/components/ui/button";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { UntrustedText } from "@/components/UntrustedText";
import { AiCancelledNote, AiWaiting } from "@/components/AiWaiting";
import { DocRef } from "@/components/DocRef";
import { useAiCall } from "@/lib/useAiCall";

export const POLICY_UNAVAILABLE = "정책 근거 추천은 정책 자료 적재 뒤 열립니다.";

/** ① 정책 근거 추천 — 제안자가 [추천 받기]를 누를 때 부른다(시간 제한 없음, 기다리는 동안 경과 초와 [취소]).
 *  404/405/503 이면 영역을 접고 한 줄 안내만. 정책 자료(국토부 계획·공사 경영목표·전략·감사 지적·정부 R&D 공고)만 —
 *  사전정보공표 연구용역(사내 발주)은 나오지 않는다(ADR 0040). 인용은 통문장, 원문 링크는 아래 "원문" 으로만.
 *  고른 문구는 제안자가 눌렀을 때만 정책 근거 칸 뒤에 덧붙는다(자동 반영 없음). */
export function PolicySuggestions({ request, onPick }: { request: ProposalRequest; onPick: (text: string) => void }) {
  const call = useAiCall((req: ProposalRequest, signal) => fetchPolicySuggestions(req, signal));
  const data: PolicyProbe | undefined = call.data;
  // 서버가 필수 4칸으로 검색한다 — 비어 있으면 422 라 부르지 않는다
  const ready = Boolean(request.current_state && request.root_cause && request.limitation && request.goal);
  if (data?.state === "unavailable") {
    return (
      <p className="text-xs text-muted-foreground" role="status">
        {POLICY_UNAVAILABLE}
      </p>
    );
  }
  const run = () => void call.run(request);
  return (
    <section aria-labelledby="policy-h" className="space-y-3 rounded-lg border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="policy-h" className="flex items-center gap-2 text-base font-semibold">
          <BookMarked className="size-4" aria-hidden="true" />
          정책 근거 추천
        </h2>
        <Button variant="outline" size="sm" onClick={run} disabled={call.pending || !ready}>
          <RefreshCw className={call.pending ? "animate-spin" : ""} aria-hidden="true" />
          {data ? "다시 받기" : "추천 받기"}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        정책 자료에서 찾은 문구입니다 — 국토부 계획·공사 경영목표·전략·감사 지적·정부 R&amp;D 공고(수집 자료, 비신뢰). 고른 것만 정책 근거 칸 뒤에 덧붙습니다 — 자동으로 넣지 않습니다.
      </p>
      {!ready && <p className="text-xs text-muted-foreground">필수 4칸(현황·원인·한계·목표)을 채운 뒤 추천을 받을 수 있습니다.</p>}
      <AiWaiting pending={call.pending} elapsed={call.elapsed} onCancel={call.cancel} what="정책 근거 추천" />
      <AiCancelledNote show={call.cancelled} />
      {call.pending ? (
        <SkeletonBlock lines={2} />
      ) : call.error ? (
        <ProblemBanner error={call.error} onRetry={run} />
      ) : data?.state === "error" ? (
        <ProblemBanner error={data.error} onRetry={run} />
      ) : data?.state === "ok" && data.items.length === 0 ? (
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground" role="status">
          <span>해당 없음 — 아이디어와 관련된 정책 문구를 찾지 못했습니다. 목표를 더 구체적으로 적으면 나아집니다.</span>
          <Button size="sm" variant="outline" onClick={run}>
            다시 시도
          </Button>
        </div>
      ) : data?.state === "ok" ? (
        <ul className="space-y-2" aria-label="정책 근거 추천 목록">
          {data.items.map((s, i) => (
            <li key={i} className="flex flex-wrap items-start justify-between gap-2 rounded-md border bg-card p-3 text-sm">
              <div className="min-w-0 flex-1 space-y-1">
                <blockquote className="border-l-2 pl-2">
                  <UntrustedText as="p" text={`“${s.quote}”`} />
                </blockquote>
                <div className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
                  <DocRef docRef={{ doc_id: s.doc_id, title: s.document, source: s.source, source_label: s.source_label, url: s.url, summary: s.quote }} compact />
                  {s.year ? <span>· {s.year}</span> : null}
                  {s.page ? (
                    <span>
                      · <UntrustedText text={String(s.page)} />
                    </span>
                  ) : null}
                  {s.url && (
                    <a href={s.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-0.5 underline">
                      · 원문 <ExternalLink className="size-3" aria-hidden="true" />
                    </a>
                  )}
                </div>
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
