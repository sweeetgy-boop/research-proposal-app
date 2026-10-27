import { useNavigate } from "react-router";
import { IdeaForm } from "@/features/idea/IdeaForm";
import { QuickInput } from "@/features/idea/QuickInput";
import { PolicySuggestions } from "@/features/idea/PolicySuggestions";
import { resetIdea, updateIdea, updateRequest, useIdea } from "@/features/idea/store";
import { usePrecheck } from "@/api/hooks";
import { ProblemBanner } from "@/components/ProblemBanner";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import type { ProposalRequest } from "@/api/types";
import { cn } from "@/lib/utils";

const MODES = [
  { id: "quick", label: "간편 입력" },
  { id: "detail", label: "상세 입력(4칸)" },
] as const;

export default function Idea() {
  const idea = useIdea();
  const navigate = useNavigate();
  const precheck = usePrecheck();
  const { toast } = useToast();
  const mode = idea.inputMode;

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
        comparison: null,
        brief: null,
        priorityEvidence: [],
      });
      navigate("/new/precheck");
    } catch {
      /* ProblemBanner 가 보여 준다 */
    }
  };

  const appendPolicy = (text: string) => {
    const cur = idea.request.policy_basis ?? "";
    updateRequest({ policy_basis: cur ? `${cur}\n${text}` : text });
    if (mode === "quick") updateIdea({ inputMode: "detail" });
    toast("정책 근거 칸에 덧붙였습니다. 상세 입력에서 확인하십시오.", "success");
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">① 아이디어 입력</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {mode === "quick" ? "한두 문장만 적으면 네 칸으로 나누어 드립니다. 입력은 유사과제 확인과 초안 생성에만 쓰입니다." : "현재 상황·원인·한계·목표 네 가지는 필수입니다. 입력은 유사과제 확인과 초안 생성에만 쓰입니다."}
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={() => resetIdea()}>
          입력 비우기
        </Button>
      </div>

      <div role="radiogroup" aria-label="입력 방식" className="flex flex-wrap gap-1">
        {MODES.map((m) => {
          const on = mode === m.id;
          return (
            <label
              key={m.id}
              className={cn(
                "inline-flex min-h-10 cursor-pointer items-center gap-1.5 rounded-md border px-3 text-sm font-medium has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring",
                on ? "border-primary bg-primary text-primary-foreground" : "hover:bg-accent",
              )}
            >
              <input type="radio" name="input-mode" value={m.id} checked={on} onChange={() => updateIdea({ inputMode: m.id })} className="sr-only" />
              {m.label}
            </label>
          );
        })}
      </div>

      <ProblemBanner error={precheck.error} />
      {mode === "quick" ? (
        <QuickInput
          text={idea.quickText}
          title={idea.quickTitle}
          onTextChange={(v) => updateIdea({ quickText: v })}
          onTitleChange={(v) => updateIdea({ quickTitle: v })}
          onFilled={(fields, title) => {
            updateIdea({ request: { ...idea.request, ...fields, title_hint: title || idea.request.title_hint }, inputMode: "detail" });
            toast("네 칸을 상세 입력에 채웠습니다. 확인·수정한 뒤 유사과제 확인으로 가십시오.", "success");
          }}
          onUnavailable={() => updateIdea({ inputMode: "detail" })}
        />
      ) : (
        <IdeaForm value={idea.request} onChange={updateRequest} onSubmit={onSubmit} busy={precheck.isPending} />
      )}

      <PolicySuggestions request={idea.request} onPick={appendPolicy} />
    </div>
  );
}
