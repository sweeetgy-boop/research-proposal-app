import * as React from "react";
import { Navigate, useNavigate } from "react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import { MessageCircleQuestion } from "lucide-react";
import { clarifyV2, ideaPolicyCards, ideaPolicyPolish } from "@/api/editai";
import { useSubmitRun } from "@/api/hooks";
import { resetIdea, updateIdea, useIdea } from "@/features/idea/store";
import { PolicyCards } from "@/features/policy/PolicyCards";
import { setPolicyChoice, usePolicyChoice } from "@/features/policy/store";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { supplementFromAnswers } from "@/lib/validation";
import type { ClarifyOutV2, RunIn, RunInEditAI } from "@/api/types";

const SOURCE_LABEL: Record<ClarifyOutV2["source"], string> = {
  argon: "Argon 이 물음",
  local: "로컬 모델이 대신 물음",
  rule: "앱 점검 질문",
  none: "",
};

/** 질문이 없을 때 사유 — 꺼짐 / 생성 실패(다시 시도) / 입력 충분 */
function headline(data: ClarifyOutV2 | undefined, n: number): string {
  if (!data) return "질문을 준비하는 중";
  if (n) return `질문 ${n}개`;
  if (data.status === "off") return "보강 질문 없음 — 꺼져 있음";
  if (data.status === "failed") return "보강 질문 없음 — 질문 생성 실패";
  return "보강 질문 없음 — 입력 충분";
}

export default function Clarify() {
  const idea = useIdea();
  const policyChoice = usePolicyChoice();
  const navigate = useNavigate();
  const submitRun = useSubmitRun();
  const [answers, setAnswers] = React.useState<Record<string, string>>({});
  const [showPolicy, setShowPolicy] = React.useState(false);
  const started = React.useRef(false); // 생성 요청 뒤 입력을 비울 때 /new 로 되돌아가지 않도록

  const q = useQuery({
    queryKey: ["clarify", idea.request],
    queryFn: () => clarifyV2(idea.request),
    enabled: !!idea.precheck,
    staleTime: Infinity,
  });
  const data = q.data;
  const questions = (data?.questions ?? []).filter((x) => x.topic !== "policy");
  const policyQuestion = (data?.questions ?? []).find((x) => x.topic === "policy");
  const policyOpen = !!policyQuestion || showPolicy || !!policyChoice;

  const start = useMutation({
    mutationFn: async (withAnswers: boolean) => {
      const pairs = withAnswers ? questions.map((x) => ({ question: x.question, answer: answers[x.id] ?? "" })) : [];
      const supplement = [idea.request.supplement ?? "", supplementFromAnswers(pairs)].filter(Boolean).join("\n");
      updateIdea({ clarifyAnswers: pairs });
      const body: RunInEditAI = {
        ...idea.request,
        supplement,
        differentiation_transfer: idea.differentiationTransfer,
        recommendation_id: idea.recommendationIndex !== null ? idea.recommendationId : null,
        recommendation_index: idea.recommendationIndex,
        acknowledged: idea.acknowledged, // 차단 경보 확인 — 서버도 같은 게이트(409)를 둔다
        priority_evidence: idea.priorityEvidence.length ? idea.priorityEvidence : null,
        policy_choice: policyChoice,
      };
      return submitRun.mutateAsync(body as RunIn);
    },
    onSuccess: (state) => {
      started.current = true;
      navigate(`/runs/${state.run_id}`, { replace: true, state: { created: true } });
      resetIdea();
      setPolicyChoice(null);
    },
  });

  if (!started.current) {
    if (!idea.precheck) return <Navigate to="/new" replace />;
    if (idea.precheck.blocking && !idea.acknowledged) return <Navigate to="/new/precheck" replace />;
  }

  const total = questions.length + (policyQuestion ? 1 : 0);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">③ 보강 질문</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          초안을 쓰기 전에 모자란 정보를 묻습니다(Argon 먼저, 실패하면 로컬 모델). 답은 입력의 "보충 정보"에 "질문: 답" 줄로 들어갑니다. 건너뛸 수 있습니다.
        </p>
      </div>
      <ProblemBanner error={q.error} onRetry={() => q.refetch()} />
      <ProblemBanner error={start.error} />
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2 text-base">
            <MessageCircleQuestion className="size-5" aria-hidden="true" />
            {q.isPending ? "질문을 준비하는 중" : headline(data, total)}
            {data && total > 0 && SOURCE_LABEL[data.source] && <Badge variant="outline">{SOURCE_LABEL[data.source]}</Badge>}
          </CardTitle>
          {!q.isPending && data && total === 0 && (
            <CardDescription>
              {data.status === "off" && "보강 단계가 꺼져 있습니다. 바로 생성합니다."}
              {data.status === "enough" && "입력이 충분해 물을 것이 없습니다. 바로 생성합니다."}
              {data.status === "failed" && `질문을 만들지 못했습니다 (${data.reason_label ?? "호출 실패"}). 다시 시도하거나 바로 생성할 수 있습니다.`}
            </CardDescription>
          )}
        </CardHeader>
        <CardContent className="space-y-5">
          {q.isPending ? (
            <SkeletonBlock lines={3} />
          ) : (
            <>
              {data && (data.status === "failed" || (data.source === "rule" && data.reason)) && (
                <Alert variant="warning" role="status">
                  <div className="flex-1">
                    <AlertTitle>{data.status === "failed" ? "질문 생성 실패" : "모델이 답하지 못해 앱 점검 질문만 보입니다"}</AlertTitle>
                    <AlertDescription>사유: {data.reason_label ?? "호출 실패"}</AlertDescription>
                    <Button size="sm" variant="outline" className="mt-2" onClick={() => q.refetch()} disabled={q.isFetching}>
                      {q.isFetching ? "다시 묻는 중…" : "다시 시도"}
                    </Button>
                  </div>
                </Alert>
              )}
              <form
                id="clarify-form"
                className="space-y-5"
                onSubmit={(e) => {
                  e.preventDefault();
                  start.mutate(true);
                }}
              >
                {questions.map((x) => (
                  <div key={x.id} className="space-y-1.5">
                    <Label htmlFor={`a-${x.id}`}>
                      <span className="mr-1 text-xs text-muted-foreground">[{x.topic_label}]</span>
                      {x.question}
                    </Label>
                    {x.hint && <p className="text-xs text-muted-foreground">{x.hint}</p>}
                    <Textarea id={`a-${x.id}`} rows={2} value={answers[x.id] ?? ""} onChange={(e) => setAnswers((s) => ({ ...s, [x.id]: e.target.value }))} />
                  </div>
                ))}
              </form>
              {policyQuestion && (
                <p className="text-sm font-medium">
                  <span className="mr-1 text-xs text-muted-foreground">[{policyQuestion.topic_label}]</span>
                  {policyQuestion.question}
                </p>
              )}
              {policyOpen ? (
                <PolicyCards
                  load={(exclude, signal) => ideaPolicyCards({ ...idea.request, exclude_doc_ids: exclude }, signal)}
                  polish={(choice, text, signal) => ideaPolicyPolish(idea.request, choice, text, signal)}
                  value={policyChoice}
                  onChoose={(c) => setPolicyChoice(c)}
                  busy={start.isPending}
                />
              ) : (
                <Button variant="outline" size="sm" onClick={() => setShowPolicy(true)}>
                  정책적 중요도 작성안 보기
                </Button>
              )}
              <div className="flex flex-wrap justify-end gap-2">
                <Button type="button" variant="outline" onClick={() => navigate("/new/brief")} disabled={start.isPending}>
                  ← 브리핑
                </Button>
                {questions.length > 0 && (
                  <Button type="button" variant="secondary" onClick={() => start.mutate(false)} disabled={start.isPending}>
                    건너뛰고 생성
                  </Button>
                )}
                <Button type="submit" form="clarify-form" disabled={start.isPending}>
                  {start.isPending ? "생성 요청 중…" : questions.length ? "답하고 생성 시작" : "초안 생성 시작"}
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
