import * as React from "react";
import { Navigate, useNavigate } from "react-router";
import { ShieldAlert, ShieldCheck } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { applyRecommendation, ntisOutcomes } from "@/api/endpoints";
import { comparisonFlow, differentiateFlow, judgePrecheck, recommendFlow, recommendMore } from "@/api/endpoints-precheck";
import type { PlanField, PlanRecommendation, PrecheckFlowOut, PrecheckOut, PrecheckRequest, SimilarChoiceValue } from "@/api/types";
import { getIdea, updateIdea, useIdea } from "@/features/idea/store";
import { RelatedResearchList } from "@/features/idea/RelatedResearchList";
import { DifferentiationPanel } from "@/features/idea/DifferentiationPanel";
import { NtisInsights } from "@/features/idea/NtisInsights";
import { LiveSearchPanel } from "@/features/live/LiveSearchPanel";
import { SimilarRowsTable } from "@/features/precheck/SimilarRowsTable";
import { JudgmentNotice } from "@/features/precheck/JudgmentNotice";
import { ComparisonView } from "@/features/precheck/ComparisonView";
import { PlanCards } from "@/features/precheck/PlanCards";
import { PlanEditor } from "@/features/precheck/PlanEditor";
import { SummaryBar } from "@/features/precheck/SummaryBar";
import { StepNavBar } from "@/components/StepNavBar";
import {
  GATE_REASON,
  RELEASED_NOTE,
  addVersion,
  cardFields,
  choiceCounts,
  choiceList,
  choicesSignature,
  effectiveBlocking,
  fullSignature,
  planFields,
  released as isReleased,
  withDefaults,
  type ChoiceMap,
} from "@/features/precheck/model";
import { NATIONAL_RND } from "@/lib/tiers";
import { useAiCall, useElapsed } from "@/lib/useAiCall";
import { AiCancelledNote, AiWaiting } from "@/components/AiWaiting";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { ProblemBanner } from "@/components/ProblemBanner";
import { useToast } from "@/components/ui/toast";
import { Eyebrow } from "@/components/ui/eyebrow";

const currentPre = () => getIdea().precheck as unknown as PrecheckFlowOut | null;
const setPre = (next: PrecheckFlowOut, patch: Parameters<typeof updateIdea>[0] = {}) =>
  updateIdea({ precheck: next as unknown as PrecheckOut, similarChoices: getIdea().similarChoices, ...patch });

/** ② 유사과제 확인 (v3, ADR 0039) — 표 먼저(규칙 판정) → AI 판정이 오면 행마다 채움 + "다르다" 행만 [관련 없음] 미리
 *  고름 → 과제안은 표가 보이자마자 뒤에서 만든다(서버는 AI 판정을 기다려 근거로 씀). 선택은 [선택 적용] 을 눌러야
 *  비교표·활용 제안·과제안 근거에 반영된다. AI 호출은 모두 시간 제한 없이 "경과 n초 [취소]". */
export default function Precheck() {
  const idea = useIdea();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { toast } = useToast();
  const pre = idea.precheck as PrecheckFlowOut | null;
  const choices = idea.similarChoices;
  const applied: ChoiceMap = idea.appliedChoices ?? {};
  const [editing, setEditing] = React.useState(false);
  const [defaultsAdded, setDefaultsAdded] = React.useState(0);

  // 서버로 보내는 입력 = 입력 + 가제(간편 입력 가제가 있으면) + 행별 선택
  const base = React.useMemo(
    () => ({ ...idea.request, title_hint: idea.request.title_hint || idea.quickTitle || "" }),
    [idea.request, idea.quickTitle],
  );
  const req: PrecheckRequest = React.useMemo(() => ({ ...base, similar_choices: choiceList(choices) }), [base, choices]);
  // [선택 적용] 한 선택 — 비교표·활용 제안·과제안은 이 입력으로
  const appliedReq: PrecheckRequest = React.useMemo(() => ({ ...base, similar_choices: choiceList(applied) }), [base, applied]);
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

  // ── AI 같음 판정 (표 먼저 뒤) ──
  const judge = useAiCall((args: { r: PrecheckRequest; retry: boolean }, signal: AbortSignal) => judgePrecheck(args.r, args.retry, signal));
  const runJudge = async (retry: boolean) => {
    const out = await judge.run({ r: req, retry });
    const cur = currentPre();
    if (!out?.alerts || !cur) return;
    // 판정 응답에는 실시간 검색 표시가 없다 — 표 먼저 응답의 live 를 이어받는다
    const live = new Set(cur.alerts.filter((a) => a.live).map((a) => a.doc_id));
    const alerts = out.alerts.map((a) => (live.has(a.doc_id) ? { ...a, live: true } : a));
    const { map, added } = withDefaults(getIdea().similarChoices, out.default_choices, alerts);
    setDefaultsAdded(added);
    setPre(
      {
        ...cur,
        alerts,
        judgment: out.judgment,
        default_choices: out.default_choices,
        core_keywords: out.core_keywords ?? cur.core_keywords,
        blocking: effectiveBlocking(alerts, map),
      },
      { similarChoices: map },
    );
    if (retry) toast(out.judgment?.retry_available ? "AI 판정이 다시 실패했습니다 — 규칙 기준을 유지합니다." : "AI 판정을 다시 받았습니다.", out.judgment?.retry_available ? "error" : "success");
  };

  // ── 차별화 과제안 (표가 보이자마자 뒤에서) ──
  const cards = useAiCall((r: PrecheckRequest, signal: AbortSignal) => recommendFlow(r, signal));
  const runCards = async (r: PrecheckRequest, used: ChoiceMap) => {
    const out = await cards.run(r);
    const cur = currentPre();
    if (!out || !cur) return;
    setPre({ ...cur, recommendations: out.recommendations }, {
      recommendationId: out.recommendations?.id ?? null,
      recommendationIndex: null,
      planSig: choicesSignature(used),
    });
  };
  const more = useAiCall((args: { r: PrecheckRequest; id: string }, signal: AbortSignal) => recommendMore(args.r, args.id, signal));
  const runMore = async () => {
    const id = pre?.recommendations?.id;
    if (!id) return;
    const before = pre?.recommendations?.recommendations.length ?? 0;
    const out = await more.run({ r: appliedReq, id });
    const cur = currentPre();
    if (!out?.recommendations || !cur) return;
    setPre({ ...cur, recommendations: out.recommendations });
    const added = out.recommendations.added ?? 0;
    if (added > 0) {
      toast(`차별화 과제안 ${added}건을 더 만들었습니다.`, "success");
      window.requestAnimationFrame(() => document.getElementById(`rec-${before}`)?.scrollIntoView?.({ behavior: "smooth", block: "center" }));
    } else {
      toast(out.recommendations.added_reason ?? "새 과제안을 만들지 못했습니다 — 다시 시도하십시오.", "error");
    }
  };

  // 화면에 처음 들어오면(새 확인 결과) AI 판정과 과제안을 바로 시작한다
  const started = React.useRef(false);
  React.useEffect(() => {
    if (!pre || started.current) return;
    started.current = true;
    if (pre.judgment?.status === "pending") void runJudge(false);
    if (!pre.recommendations) void runCards({ ...appliedReq }, applied);
  }, [pre]);

  // ── 차별성 비교표 — [선택 적용] 한 [유사함] 행만 ──
  const cmpKey = ["comparison-flow", appliedReq] as const;
  const cmp = useQuery({
    queryKey: cmpKey,
    queryFn: ({ signal }) => comparisonFlow(appliedReq, signal),
    enabled: !!pre,
    staleTime: Infinity,
    retry: false,
  });
  const cmpFetching = cmp.fetchStatus === "fetching";
  const cmpElapsed = useElapsed(cmpFetching);
  const hasNtis = !!pre?.alerts.some((a) => a.tier === NATIONAL_RND);
  const ntis = useQuery({
    queryKey: ["ntis-outcomes", idea.request],
    queryFn: () => ntisOutcomes(idea.request),
    enabled: !!pre && hasNtis && !cmpFetching,
    staleTime: Infinity,
    retry: false,
  });

  // ── 활용·차별화 제안 — [선택 적용] 한 [유사함] 행만 ──
  const diff = useAiCall((r: PrecheckRequest, signal: AbortSignal) => differentiateFlow(r, signal));
  const runDifferentiate = async (r: PrecheckRequest) => {
    const out = await diff.run(r);
    const cur = currentPre();
    if (!out || !cur) return;
    const d = out.differentiation;
    setPre({ ...cur, differentiation: d }, {
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
  };

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
  const counts = choiceCounts(pre.alerts, choices);
  const appliedCounts = choiceCounts(pre.alerts, applied);
  const choicesStale = fullSignature(choices) !== fullSignature(applied);
  const planStale = idea.planSig !== null && idea.planSig !== choicesSignature(applied) && !cards.pending;

  const choose = (docId: string, value: SimilarChoiceValue | null) => {
    const next = { ...choices };
    // 묶음 행(같은 제목·같은 연작, ADR 0043)의 선택은 행 하나 — 구성원 doc_id 로 남은 옛 선택은 지운다
    const row = pre.alerts.find((a) => a.doc_id === docId);
    for (const id of row?.merged_ids ?? []) delete next[id];
    if (value) next[docId] = value;
    else delete next[docId];
    updateIdea({
      similarChoices: next,
      precheck: { ...pre, blocking: effectiveBlocking(pre.alerts, next) } as unknown as PrecheckOut,
    });
  };

  // [선택 적용] — 비교표·활용 제안·과제안 근거를 지금 선택으로 다시 만든다
  const applyChoices = () => {
    const now = { ...choices };
    const r: PrecheckRequest = { ...base, similar_choices: choiceList(now) };
    updateIdea({ appliedChoices: now, similarChoices: now, differentiationTransfer: null });
    const sim = choiceCounts(pre.alerts, now).similar;
    if (sim > 0) void runDifferentiate(r);
    else {
      diff.cancel();
      const cur = currentPre();
      if (cur) setPre({ ...cur, differentiation: undefined });
    }
    if (choicesSignature(now) !== idea.planSig || !pre.recommendations) void runCards(r, now);
    toast("선택을 적용했습니다 — 비교표를 다시 만듭니다.", "success");
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
        <Eyebrow className="mb-1">Step 02 · Similar projects</Eyebrow>
        <h1 className="text-2xl font-bold tracking-tight">② 유사과제 확인</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          관련도와 아이디어 핵심 키워드로 찾은 기존 과제(사내 기록·알리오·NTIS 과제·발주 용역)입니다. 표를 먼저 보이고 AI 판정이 오면 행마다 채웁니다. 행마다
          [유사함]·[관련 없음] 을 고른 뒤 [선택 적용] 을 누르면 비교표·활용 제안·차별화 과제안에 [유사함] 과제만 쓰입니다. 제목은 수집 자료의 텍스트입니다.
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
          유사과제 {pre.alerts.length}건 <span className="text-sm font-normal text-muted-foreground">· 유사함 {counts.similar}건</span>
        </h2>
        <JudgmentNotice
          judgment={pre.judgment}
          coreKeywords={pre.core_keywords}
          onRetry={() => void runJudge(pre.judgment?.status !== "pending")}
          retrying={judge.pending}
          elapsed={judge.elapsed}
          onCancel={judge.cancel}
          cancelled={judge.cancelled}
          defaultsAdded={defaultsAdded}
        />
        <ProblemBanner error={judge.error} />
        <SimilarRowsTable alerts={pre.alerts} choices={choices} onChoose={choose} judging={judge.pending} />
      </section>

      {pre.related_research ? <RelatedResearchList items={pre.related_research} /> : null}
      {pre.live_search ? <LiveSearchPanel live={pre.live_search} /> : null}
      {hasNtis ? <NtisInsights data={ntis.data} loading={ntis.isPending} unavailable={!!ntis.error} /> : null}

      <div className="space-y-2">
        <AiWaiting pending={cmpFetching} elapsed={cmpElapsed} onCancel={() => void qc.cancelQueries({ queryKey: cmpKey })} what="비교표 만들기" />
        <ComparisonView data={cmp.data?.comparison} loading={cmp.isPending && cmpFetching} error={cmp.error} onRetry={() => cmp.refetch()} />
      </div>

      <div className="space-y-2">
        <AiWaiting pending={diff.pending} elapsed={diff.elapsed} onCancel={diff.cancel} what="활용·차별화 제안" />
        <AiCancelledNote show={diff.cancelled && !diff.pending} />
        <ProblemBanner error={diff.error} />
        <DifferentiationPanel
          diff={pre.differentiation}
          loading={diff.pending}
          onRequest={() => void runDifferentiate(appliedReq)}
          picked={idea.request.differentiation ?? ""}
          similarCount={appliedCounts.similar}
          onPick={(text) => {
            updateIdea({ request: { ...idea.request, differentiation: text }, similarChoices: choices });
            toast("차별화 방향을 입력에 반영했습니다.", "success");
          }}
        />
      </div>

      <ProblemBanner error={cards.error ?? more.error ?? pickM.error} />
      <PlanCards
        rec={pre.recommendations}
        waiting={{ pending: cards.pending, elapsed: cards.elapsed, cancelled: cards.cancelled, onCancel: cards.cancel }}
        chosenIndex={idea.recommendationIndex}
        stale={planStale}
        onPick={(card) => pickM.mutate(card)}
        onKeepOriginal={keepOriginal}
        onWrite={() => setEditing(true)}
        onRegenerate={() => void runCards(appliedReq, applied)}
      />
      {editing && (
        <PlanEditor request={req} initial={planFields(idea.request)} original={original} onConfirm={confirmEdit} onCancel={() => setEditing(false)} />
      )}

      <SummaryBar
        similar={counts.similar}
        unrelated={counts.unrelated}
        stale={choicesStale}
        applied={idea.appliedChoices !== null}
        applying={false}
        onApply={applyChoices}
        onMore={() => void runMore()}
        moreDisabled={!pre.recommendations?.id || cards.pending}
        morePending={more.pending}
        moreElapsed={more.elapsed}
        onCancelMore={more.cancel}
      />
      {/* 레인 D 항목 22: 아래 이동 막대 — ② 게이트(차단 행을 고르기 전에는 다음으로 못 간다)를 막대에 넣는다 */}
      <StepNavBar
        prev={{ label: "이전 단계: 아이디어 입력", to: "/new" }}
        next={{ label: "다음: 선행연구 브리핑", onClick: next, reason: gateOk ? null : GATE_REASON }}
      />
    </div>
  );
}
