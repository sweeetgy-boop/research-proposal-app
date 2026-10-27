import * as React from "react";
import { Navigate, useNavigate } from "react-router";
import { ShieldAlert } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { comparison, differentiate, ntisOutcomes, recommend } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import { ComparisonTable } from "@/features/idea/ComparisonTable";
import type { RecommendationPreview } from "@/api/types";
import { updateIdea, updateRequest, useIdea } from "@/features/idea/store";
import { AlertsTable } from "@/features/idea/AlertsTable";
import { RelatedResearchList } from "@/features/idea/RelatedResearchList";
import { RecommendationCards } from "@/features/idea/RecommendationCards";
import { DifferentiationPanel } from "@/features/idea/DifferentiationPanel";
import { NtisInsights } from "@/features/idea/NtisInsights";
import { NATIONAL_RND } from "@/lib/tiers";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { ProblemBanner } from "@/components/ProblemBanner";
import { useToast } from "@/components/ui/toast";

export default function Precheck() {
  const idea = useIdea();
  const navigate = useNavigate();
  const { toast } = useToast();
  const pre = idea.precheck;

  // U4 차별성 비교표 — 입력이 바뀌면 다시 받는다 (LLM 없음)
  const cmp = useQuery({
    queryKey: ["comparison", idea.request],
    queryFn: () => comparison(idea.request),
    enabled: !!pre,
    staleTime: Infinity,
    retry: false,
  });
  // NTIS 과제(tier national_rnd)가 알림에 있을 때만 1회 — 503·오류는 한 줄 안내, 흐름을 막지 않는다.
  // 비교표가 끝난 뒤에 보낸다: 두 경로 모두 서버에서 precheck(reranker)를 다시 돌리므로 동시에 보내지 않는다
  const hasNtis = !!pre?.alerts.some((a) => a.tier === NATIONAL_RND);
  const ntis = useQuery({
    queryKey: ["ntis-outcomes", idea.request],
    queryFn: () => ntisOutcomes(idea.request),
    enabled: !!pre && hasNtis && !cmp.isFetching,
    staleTime: Infinity,
    retry: false,
  });
  const recFor = React.useMemo(() => {
    const m = new Map<string, number>();
    for (const r of pre?.recommendations?.recommendations ?? []) for (const d of r.compared_with) if (!m.has(d)) m.set(d, r.index);
    return m;
  }, [pre]);

  const recommendM = useMutation({
    mutationFn: () => recommend(idea.request),
    onSuccess: (out) => {
      updateIdea({
        precheck: { ...(idea.precheck ?? out), ...out, differentiation: idea.precheck?.differentiation ?? out.differentiation },
        recommendationId: out.recommendations?.id ?? null,
        recommendationIndex: null,
      });
    },
  });
  const differentiateM = useMutation({
    mutationFn: () => differentiate(idea.request),
    onSuccess: (out) => {
      const d = out.differentiation;
      updateIdea({
        precheck: { ...(idea.precheck ?? out), differentiation: d },
        differentiationTransfer: d
          ? {
              provider: d.provider,
              model: d.model,
              fallback_local: d.fallback_local,
              public_doc_ids: d.transfer.public_doc_ids,
              internal_doc_ids: d.transfer.internal_doc_ids,
              excluded_doc_ids: d.transfer.excluded_doc_ids,
              calls: d.transfer.calls,
              items: d.items.length,
              discarded: d.discarded.length,
              skipped_reason: d.skipped_reason,
            }
          : null,
      });
    },
  });

  // 자동 차별화 제안(차단 때)의 전송 기록도 run 에 남긴다
  React.useEffect(() => {
    const d = pre?.differentiation;
    if (d && !idea.differentiationTransfer) {
      updateIdea({
        differentiationTransfer: {
          provider: d.provider,
          model: d.model,
          fallback_local: d.fallback_local,
          public_doc_ids: d.transfer.public_doc_ids,
          internal_doc_ids: d.transfer.internal_doc_ids,
          excluded_doc_ids: d.transfer.excluded_doc_ids,
          calls: d.transfer.calls,
          items: d.items.length,
          discarded: d.discarded.length,
          skipped_reason: d.skipped_reason,
        },
      });
    }
  }, [pre, idea.differentiationTransfer]);

  if (!pre) return <Navigate to="/new" replace />;

  const gateOk = !pre.blocking || idea.acknowledged;

  const chooseRecommendation = (index: number, preview: RecommendationPreview) => {
    updateIdea({ request: { ...idea.request, ...preview.request }, recommendationIndex: index });
    toast(`추천 ${index + 1}번을 입력에 반영했습니다. 가제·목표를 확인한 뒤 진행하십시오.`, "success");
  };

  const next = () => navigate("/new/brief");

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">② 유사과제 확인</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          유사도와 공유 키워드가 함께 기준을 넘는 기존 과제(사내 기록·알리오·NTIS 과제·발주 용역)입니다. 제목은 수집 자료의 텍스트입니다.
        </p>
      </div>

      {pre.blocking && (
        <Alert variant="destructive" role="alert">
          <ShieldAlert aria-hidden="true" />
          <div className="flex-1 space-y-3">
            <div>
              <AlertTitle>차단 경보 — 중복 가능성이 높은 과제가 있습니다</AlertTitle>
              <AlertDescription>
                그대로 제출하면 심사에서 중복으로 걸릴 수 있습니다. 아래 차별화 제안·과제 추천을 보고 방향을 정하거나, 알고도 진행하려면 확인란에 표시하십시오.
              </AlertDescription>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox id="ack" checked={idea.acknowledged} onChange={(e) => updateIdea({ acknowledged: e.target.checked })} />
              <Label htmlFor="ack">차단 경보를 확인했고 그래도 진행합니다</Label>
            </div>
          </div>
        </Alert>
      )}

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">유사과제 {pre.alerts.length}건</h2>
        <AlertsTable alerts={pre.alerts} />
      </section>

      {pre.related_research ? <RelatedResearchList items={pre.related_research} /> : null}

      {hasNtis ? <NtisInsights data={ntis.data} loading={ntis.isPending} unavailable={!!ntis.error} /> : null}

      <ComparisonTable
        data={cmp.data?.comparison}
        loading={cmp.isPending}
        error={isApiError(cmp.error) && cmp.error.status === 503 ? null : cmp.error}
        unavailable={isApiError(cmp.error) && cmp.error.status === 503}
        onRetry={() => cmp.refetch()}
        recommendationFor={recFor}
      />

      <ProblemBanner error={differentiateM.error} />
      <DifferentiationPanel
        diff={pre.differentiation}
        loading={differentiateM.isPending}
        onRequest={() => differentiateM.mutate()}
        picked={idea.request.differentiation ?? ""}
        onPick={(text) => {
          updateRequest({ differentiation: text });
          toast("차별화 방향을 입력에 반영했습니다.", "success");
        }}
      />

      <ProblemBanner error={recommendM.error} />
      <RecommendationCards
        rec={pre.recommendations}
        chosenIndex={idea.recommendationIndex}
        onChoose={chooseRecommendation}
        onProceedOriginal={() => {
          updateIdea({ recommendationIndex: null });
          if (gateOk) next();
          else toast("차단 경보 확인란에 먼저 표시하십시오.", "error");
        }}
        onRetry={() => recommendM.mutate()}
        retrying={recommendM.isPending}
      />

      <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-4">
        <Button variant="outline" onClick={() => navigate("/new")}>
          ← 입력 고치기
        </Button>
        <Button onClick={next} disabled={!gateOk} aria-disabled={!gateOk}>
          다음: 선행연구 브리핑 →
        </Button>
      </div>
    </div>
  );
}
