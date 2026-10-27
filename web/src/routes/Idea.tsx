import { useNavigate } from "react-router";
import { IdeaForm } from "@/features/idea/IdeaForm";
import { resetIdea, updateIdea, updateRequest, useIdea } from "@/features/idea/store";
import { usePrecheck } from "@/api/hooks";
import { ProblemBanner } from "@/components/ProblemBanner";
import { Button } from "@/components/ui/button";
import type { ProposalRequest } from "@/api/types";

export default function Idea() {
  const idea = useIdea();
  const navigate = useNavigate();
  const precheck = usePrecheck();

  const onSubmit = async (req: ProposalRequest) => {
    try {
      const budget = req.budget && (req.budget.account || req.budget.amount_thousand_krw !== null) ? req.budget : null;
      const clean = { ...req, budget };
      const out = await precheck.mutateAsync(clean);
      updateIdea({
        request: clean,
        precheck: out,
        acknowledged: false,
        recommendationId: out.recommendations?.id ?? null,
        recommendationIndex: null,
        differentiationTransfer: null,
        clarifyAnswers: [],
      });
      navigate("/new/precheck");
    } catch {
      /* ProblemBanner 가 보여 준다 */
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">① 아이디어 입력</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            현재 상황·원인·한계·목표 네 가지는 필수입니다. 입력은 유사과제 확인과 초안 생성에만 쓰입니다.
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={() => resetIdea()}>
          입력 비우기
        </Button>
      </div>
      <ProblemBanner error={precheck.error} />
      <IdeaForm value={idea.request} onChange={updateRequest} onSubmit={onSubmit} busy={precheck.isPending} />
    </div>
  );
}
