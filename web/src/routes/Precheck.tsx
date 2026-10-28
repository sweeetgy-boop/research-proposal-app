import * as React from "react";
import { Navigate, useNavigate } from "react-router";
import { ShieldAlert, ShieldCheck } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { applyRecommendation, ntisOutcomes } from "@/api/endpoints";
import { comparisonFlow, differentiateFlow, recommendFlow, retryJudgment } from "@/api/endpoints-precheck";
import type { PlanField, PlanRecommendation, PrecheckFlowOut, PrecheckOut, PrecheckRequest, SimilarChoiceValue } from "@/api/types";
import { updateIdea, useIdea } from "@/features/idea/store";
import { RelatedResearchList } from "@/features/idea/RelatedResearchList";
import { DifferentiationPanel } from "@/features/idea/DifferentiationPanel";
import { NtisInsights } from "@/features/idea/NtisInsights";
import { LiveSearchPanel } from "@/features/live/LiveSearchPanel";
import { SimilarRowsTable } from "@/features/precheck/SimilarRowsTable";
import { JudgmentNotice } from "@/features/precheck/JudgmentNotice";
import { ComparisonView } from "@/features/precheck/ComparisonView";
import { PlanCards } from "@/features/precheck/PlanCards";
import { PlanEditor } from "@/features/precheck/PlanEditor";
import { StepNavBar } from "@/components/StepNavBar";
import {
  GATE_REASON,
  RELEASED_NOTE,
  addVersion,
  cardFields,
  choiceList,
  choicesSignature,
  effectiveBlocking,
  planFields,
  released as isReleased,
} from "@/features/precheck/model";
import { NATIONAL_RND } from "@/lib/tiers";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { ProblemBanner } from "@/components/ProblemBanner";
import { useToast } from "@/components/ui/toast";

export default function Precheck() {
  const idea = useIdea();
  const navigate = useNavigate();
  const { toast } = useToast();
  const pre = idea.precheck as PrecheckFlowOut | null;
  const choices = idea.similarChoices;
  const [editing, setEditing] = React.useState(false);

  // 서버로 보내는 입력 = 입력 + 가제(간편 입력 가제가 있으면) + 행별 선택
  const req: PrecheckRequest = React.useMemo(
    () => ({
      ...idea.request,
      title_hint: idea.request.title_hint || idea.quickTitle || "",
      similar_choices: choiceList(choices),
    }),
    [idea.request, idea.quickTitle, choices],
  );
  const original = idea.originalPlan ?? planFields(idea.request);

  React.useEffect(() => {
    if (pre && !idea.originalPlan) {
      updateIdea({
        originalPlan: planFields(idea.request),
        planSig: choicesSignature(choices),
        similarChoices: choices,
        request: { ...idea.request, idea_versions: addVersion(undefined, "original", planFields(idea.request)) },
      });
    }
  }, [pre, idea.originalPlan, idea.request, choices]);

  // 차별성 비교표 — [유사함] 행만. 선택·입력이 바뀌면 다시 받는다(서버는 판정 메모를 쓴다)
  const cmp = useQuery({
    queryKey: ["comparison-flow", req],
    queryFn: () => comparisonFlow(req),
    enabled: !!pre,
    staleTime: Infinity,
    retry: false,
  });
  const hasNtis = !!pre?.alerts.some((a) => a.tier === NATIONAL_RND);
  const ntis = useQuery({
    queryKey: ["ntis-outcomes", idea.request],
    queryFn: () => ntisOutcomes(idea.request),
    enabled: !!pre && hasNtis && !cmp.isFetching,
    staleTime: Infinity,
    retry: false,
  });

  const setPrecheck = (next: PrecheckFlowOut) => updateIdea({ precheck: next as unknown as PrecheckOut, similarChoices: choices });

  const retryM = useMutation({
    mutationFn: () => retryJudgment(req),
    onSuccess: (out) => {
      if (!pre) return;
      setPrecheck({ ...pre, alerts: out.alerts, judgment: out.judgment, blocking: out.blocking });
      toast(out.judgment?.retry_available ? "AI 판정이 다시 실패했습니다 — 규칙 기준을 유지합니다." : "AI 판정을 다시 받았습니다.", out.judgment?.retry_available ? "error" : "success");
    },
  });
  const recommendM = useMutation({
    mutationFn: () => recommendFlow(req),
    onSuccess: (out) => {
      if (!pre) return;
      setPrecheck({ ...pre, recommendations: out.recommendations });
      updateIdea({ recommendationId: out.recommendations?.id ?? null, recommendationIndex: null, planSig: choicesSignature(choices), similarChoices: choices });
    },
  });
  const differentiateM = useMutation({
    mutationFn: () => differentiateFlow(req),
    onSuccess: (out) => {
      if (!pre) return;
      const d = out.differentiation;
      setPrecheck({ ...pre, differentiation: d });
      updateIdea({
        similarChoices: choices,
        differentiationTransfer:
          d && d.items.length
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
  const pickM = useMutation({
    mutationFn: async (card: PlanRecommendation) => {
      const rid = pre?.recommendations?.id;
      if (rid) await applyRecommendation(rid, card.index); // 서버 미리보기 확인(세션 유효성) — 칸은 카드 그대로
      return card;
    },
    onSuccess: (card) => {
      const fields = cardFields(card, idea.request);
      updateIdea({
        request: { ...idea.request, ...fields, idea_versions: addVersion(idea.request.idea_versions, "card", fields, card.index) },
        recommendationIndex: card.index,
        planSource: "card",
        similarChoices: choices,
      });
      setEditing(false);
      toast(`과제안 ${card.index + 1}번을 입력에 반영했습니다. 비교표의 제안 과제 칸도 바뀝니다.`, "success");
    },
  });

  if (!pre) return <Navigate to="/new" replace />;

  const blocking = effectiveBlocking(pre.alerts, choices);
  const released = isReleased(pre.alerts, choices);
  const gateOk = !blocking || idea.acknowledged;
  const similarCount = Object.values(choices).filter((c) => c === "similar").length;
  const stale = idea.planSig !== null && idea.planSig !== choicesSignature(choices);

  const choose = (docId: string, value: SimilarChoiceValue | null) => {
    const next = { ...choices };
    if (value) next[docId] = value;
    else delete next[docId];
    const nextBlocking = effectiveBlocking(pre.alerts, next);
    updateIdea({
      similarChoices: next,
      precheck: { ...pre, blocking: nextBlocking } as unknown as PrecheckOut,
      // 선택이 바뀌면 활용 제안은 다시 받아야 한다
      differentiationTransfer: null,
    });
  };

  const keepOriginal = () => {
    updateIdea({
      request: { ...idea.request, ...original, idea_versions: addVersion(idea.request.idea_versions, "original", original) },
      recommendationIndex: null,
      planSource: "original",
      similarChoices: choices,
    });
    setEditing(false);
    toast("원래 아이디어로 진행합니다.", "success");
    if (gateOk) next();
  };

  const confirmEdit = (fields: Record<PlanField, string>) => {
    updateIdea({
      request: { ...idea.request, ...fields, idea_versions: addVersion(idea.request.idea_versions, "edited", fields) },
      recommendationIndex: null,
      planSource: "edited",
      similarChoices: choices,
    });
    setEditing(false);
    toast("고친 과제안을 입력에 반영했습니다.", "success");
  };

  function next() {
    // 차단 해제(모든 차단 행 [관련 없음])면 ③ 화면 게이트도 풀리게 precheck.blocking 을 맞춘다
    updateIdea({ precheck: { ...pre!, blocking } as unknown as PrecheckOut, similarChoices: choices, request: req });
    navigate("/new/brief");
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">② 유사과제 확인</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          관련도(reranker 점수)와 아이디어 핵심 키워드로 찾은 기존 과제(사내 기록·알리오·NTIS 과제·발주 용역)입니다. 행마다 [유사함]·[관련 없음] 을 고르면 비교표·차별화 과제안·본문 차별성 문장에 [유사함] 과제만 쓰입니다. 제목은 수집 자료의 텍스트입니다.
        </p>
      </div>

      {blocking && (
        <Alert variant="destructive" role="alert">
          <ShieldAlert aria-hidden="true" />
          <div className="flex-1 space-y-3">
            <div>
              <AlertTitle>차단 경보 — 대상·문제·방법이 같은 과제가 있습니다</AlertTitle>
              <AlertDescription>
                그대로 제출하면 심사에서 중복으로 걸릴 수 있습니다. 실제로 관련 없는 과제면 그 행에서 [관련 없음] 을 고르십시오(모두 고르면 차단이 풀립니다). 알고도 진행하려면 확인란에 표시하십시오.
              </AlertDescription>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox id="ack" checked={idea.acknowledged} onChange={(e) => updateIdea({ acknowledged: e.target.checked, similarChoices: choices })} />
              <Label htmlFor="ack">차단 경보를 확인했고 그래도 진행합니다</Label>
            </div>
          </div>
        </Alert>
      )}
      {released && (
        <Alert role="status">
          <ShieldCheck aria-hidden="true" />
          <AlertDescription>{RELEASED_NOTE}</AlertDescription>
        </Alert>
      )}

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">
          유사과제 {pre.alerts.length}건 <span className="text-sm font-normal text-muted-foreground">· 유사함 {similarCount}건</span>
        </h2>
        <JudgmentNotice judgment={pre.judgment} coreKeywords={pre.core_keywords} onRetry={() => retryM.mutate()} retrying={retryM.isPending} />
        <ProblemBanner error={retryM.error} />
        <SimilarRowsTable alerts={pre.alerts} choices={choices} onChoose={choose} />
      </section>

      {pre.related_research ? <RelatedResearchList items={pre.related_research} /> : null}
      {pre.live_search ? <LiveSearchPanel live={pre.live_search} /> : null}
      {hasNtis ? <NtisInsights data={ntis.data} loading={ntis.isPending} unavailable={!!ntis.error} /> : null}

      <ComparisonView data={cmp.data?.comparison} loading={cmp.isPending} error={cmp.error} onRetry={() => cmp.refetch()} />

      <ProblemBanner error={differentiateM.error} />
      <DifferentiationPanel
        diff={pre.differentiation}
        loading={differentiateM.isPending}
        onRequest={() => differentiateM.mutate()}
        picked={idea.request.differentiation ?? ""}
        similarCount={similarCount}
        onPick={(text) => {
          updateIdea({ request: { ...idea.request, differentiation: text }, similarChoices: choices });
          toast("차별화 방향을 입력에 반영했습니다.", "success");
        }}
      />

      <ProblemBanner error={recommendM.error ?? pickM.error} />
      <PlanCards
        rec={pre.recommendations}
        loading={recommendM.isPending}
        chosenIndex={idea.recommendationIndex}
        stale={stale}
        onPick={(card) => pickM.mutate(card)}
        onKeepOriginal={keepOriginal}
        onWrite={() => setEditing(true)}
        onRegenerate={() => recommendM.mutate()}
      />
      {editing && (
        <PlanEditor request={req} initial={planFields(idea.request)} original={original} onConfirm={confirmEdit} onCancel={() => setEditing(false)} />
      )}

      {/* 레인 D 항목 22: 아래 이동 막대 — ② 게이트(차단 행을 고르기 전에는 다음으로 못 간다)를 막대에 넣는다 */}
      <StepNavBar
        prev={{ label: "이전 단계: 아이디어 입력", to: "/new" }}
        next={{ label: "다음: 선행연구 브리핑", onClick: next, reason: gateOk ? null : GATE_REASON }}
      />
    </div>
  );
}
