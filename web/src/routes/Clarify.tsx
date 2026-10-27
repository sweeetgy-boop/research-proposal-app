import * as React from "react";
import { Navigate, useNavigate } from "react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import { MessageCircleQuestion } from "lucide-react";
import { clarify } from "@/api/endpoints";
import { useSubmitRun } from "@/api/hooks";
import { resetIdea, updateIdea, useIdea } from "@/features/idea/store";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { supplementFromAnswers } from "@/lib/validation";
import type { ClarifyQuestion, RunIn } from "@/api/types";

function normalize(q: ClarifyQuestion | string, i: number): { id: string; question: string; hint?: string } {
  if (typeof q === "string") return { id: `q${i}`, question: q };
  return { id: q.id ?? q.field ?? `q${i}`, question: q.question, hint: q.hint };
}

export default function Clarify() {
  const idea = useIdea();
  const navigate = useNavigate();
  const submitRun = useSubmitRun();
  const [answers, setAnswers] = React.useState<Record<string, string>>({});
  const started = React.useRef(false); // 생성 요청 뒤 입력을 비울 때 /new 로 되돌아가지 않도록

  const q = useQuery({
    queryKey: ["clarify", idea.request],
    queryFn: () => clarify(idea.request),
    enabled: !!idea.precheck,
    staleTime: Infinity,
  });

  const start = useMutation({
    mutationFn: async (withAnswers: boolean) => {
      const questions = (q.data?.questions ?? []).map(normalize);
      const pairs = withAnswers ? questions.map((x) => ({ question: x.question, answer: answers[x.id] ?? "" })) : [];
      const supplement = [idea.request.supplement ?? "", supplementFromAnswers(pairs)].filter(Boolean).join("\n");
      updateIdea({ clarifyAnswers: pairs });
      const body: RunIn = {
        ...idea.request,
        supplement,
        differentiation_transfer: idea.differentiationTransfer,
        recommendation_id: idea.recommendationIndex !== null ? idea.recommendationId : null,
        recommendation_index: idea.recommendationIndex,
        acknowledged: idea.acknowledged, // 차단 경보 확인 — 서버도 같은 게이트(409)를 둔다
        priority_evidence: idea.priorityEvidence.length ? idea.priorityEvidence : null,
      };
      return submitRun.mutateAsync(body);
    },
    onSuccess: (state) => {
      started.current = true;
      navigate(`/runs/${state.run_id}`, { replace: true, state: { created: true } });
      resetIdea();
    },
  });

  if (!started.current) {
    if (!idea.precheck) return <Navigate to="/new" replace />;
    if (idea.precheck.blocking && !idea.acknowledged) return <Navigate to="/new/precheck" replace />;
  }

  const questions = (q.data?.questions ?? []).map(normalize);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">③ 보강 질문</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          초안을 쓰기 전에 모자란 정보를 묻습니다. 답은 입력의 "보충 정보"에 "질문: 답" 줄로 들어갑니다. 건너뛸 수 있습니다.
        </p>
      </div>
      <ProblemBanner error={q.error} onRetry={() => q.refetch()} />
      <ProblemBanner error={start.error} />
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <MessageCircleQuestion className="size-5" aria-hidden="true" />
            {q.isPending ? "질문을 준비하는 중" : questions.length ? `질문 ${questions.length}개` : "보강 질문 없음"}
          </CardTitle>
          {!q.isPending && questions.length === 0 && (
            <CardDescription>물을 것이 없습니다 (보강 단계가 꺼져 있거나 입력이 충분합니다). 바로 생성합니다.</CardDescription>
          )}
        </CardHeader>
        <CardContent>
          {q.isPending ? (
            <SkeletonBlock lines={3} />
          ) : (
            <form
              className="space-y-5"
              onSubmit={(e) => {
                e.preventDefault();
                start.mutate(true);
              }}
            >
              {questions.map((x) => (
                <div key={x.id} className="space-y-1.5">
                  <Label htmlFor={`a-${x.id}`}>{x.question}</Label>
                  {x.hint && <p className="text-xs text-muted-foreground">{x.hint}</p>}
                  <Textarea id={`a-${x.id}`} rows={2} value={answers[x.id] ?? ""} onChange={(e) => setAnswers((s) => ({ ...s, [x.id]: e.target.value }))} />
                </div>
              ))}
              <div className="flex flex-wrap justify-end gap-2">
                <Button type="button" variant="outline" onClick={() => navigate("/new/brief")} disabled={start.isPending}>
                  ← 브리핑
                </Button>
                {questions.length > 0 && (
                  <Button type="button" variant="secondary" onClick={() => start.mutate(false)} disabled={start.isPending}>
                    건너뛰고 생성
                  </Button>
                )}
                <Button type="submit" disabled={start.isPending}>
                  {start.isPending ? "생성 요청 중…" : questions.length ? "답하고 생성 시작" : "초안 생성 시작"}
                </Button>
              </div>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
