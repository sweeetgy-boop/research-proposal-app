import * as React from "react";
import { useNavigate } from "react-router";
import { BookMarked } from "lucide-react";
import { IdeaForm } from "@/features/idea/IdeaForm";
import { QuickInput } from "@/features/idea/QuickInput";
import { POLICY_LATER_NOTE, PolicyPickDialog } from "@/features/idea/PolicyPickDialog";
import { getIdea, resetIdea, updateIdea, updateRequest, useIdea } from "@/features/idea/store";
import { mergePolicyBasis } from "@/api/policySuggestions";
import { useMutation } from "@tanstack/react-query";
import { precheckFast } from "@/api/endpoints-precheck";
import type { PrecheckOut } from "@/api/types";
import { ProblemBanner } from "@/components/ProblemBanner";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useToast } from "@/components/ui/toast";
import type { ProposalRequest } from "@/api/types";
import { cn } from "@/lib/utils";
import { StepNavBar } from "@/components/StepNavBar";
import { Eyebrow } from "@/components/ui/eyebrow";

const MODES = [
  { id: "quick", label: "간편 입력" },
  { id: "detail", label: "상세 입력(4칸)" },
] as const;

export default function Idea() {
  const idea = useIdea();
  const navigate = useNavigate();
  // ② 표 먼저 (ADR 0039) — 실시간 검색 + 규칙 판정까지. AI 판정·과제안은 ② 화면이 이어서 받는다
  const precheck = useMutation({ mutationFn: (req: ProposalRequest) => precheckFast(req) as unknown as Promise<PrecheckOut> });
  const { toast } = useToast();
  const mode = idea.inputMode;
  // 정책 근거 추천 팝업 (ADR 0052) — 네 칸이 채워질 때 자동, [다음] 때 칸이 비었으면 먼저, 칸 아래 버튼으로 언제든
  const [policyOpen, setPolicyOpen] = React.useState(false);
  const [gated, setGated] = React.useState<ProposalRequest | null>(null);

  const runPrecheck = async (req: ProposalRequest) => {
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

  const onSubmit = (req: ProposalRequest) => {
    if (!req.policy_basis?.trim() && !idea.policyDeferred) {
      setGated(req);
      setPolicyOpen(true);
      return;
    }
    void runPrecheck(req);
  };

  /** [적용] — 고른 추천·직접 입력을 칸 뒤에 덧붙인다(같은 문장은 한 번). [다음] 에서 열었으면 이어서 ② 로 */
  const applyPolicy = (additions: string[]) => {
    const merged = mergePolicyBasis(getIdea().request.policy_basis ?? "", additions);
    updateRequest({ policy_basis: merged });
    updateIdea({ policyDeferred: false });
    setPolicyOpen(false);
    toast("정책 근거 칸에 넣었습니다.", "success");
    if (gated) {
      setGated(null);
      void runPrecheck({ ...gated, policy_basis: merged });
    }
  };
  const deferPolicy = () => {
    updateIdea({ policyDeferred: true });
    setPolicyOpen(false);
    if (gated) {
      setGated(null);
      toast(POLICY_LATER_NOTE, "info");
      void runPrecheck(gated);
    }
  };
  const closePolicy = () => {
    setPolicyOpen(false);
    setGated(null);
  };
  const policyEmpty = !idea.request.policy_basis?.trim();
  const policyTools = (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant={policyEmpty ? "default" : "outline"} size="sm" onClick={() => setPolicyOpen(true)}>
          <BookMarked aria-hidden="true" />
          정책 근거 추천 열기
        </Button>
        <span className="text-xs text-muted-foreground">정책 자료에서 관련 문구를 골라 넣습니다 — [적용] 을 눌러야 칸에 들어갑니다.</span>
      </div>
      {policyEmpty && idea.policyDeferred && (
        <Alert variant="warning" data-testid="policy-later-note">
          <AlertDescription>{POLICY_LATER_NOTE}</AlertDescription>
        </Alert>
      )}
    </div>
  );

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <Eyebrow className="mb-1">Step 01 · Idea</Eyebrow>
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
            setPolicyOpen(true);
          }}
          onUnavailable={() => updateIdea({ inputMode: "detail" })}
        />
      ) : (
        <IdeaForm value={idea.request} onChange={updateRequest} onSubmit={onSubmit} busy={precheck.isPending} hideSubmit policyTools={policyTools} />
      )}

      <PolicyPickDialog open={policyOpen} request={idea.request} gate={gated !== null} onApply={applyPolicy} onLater={deferPolicy} onClose={closePolicy} />
      <StepNavBar
        next={
          mode === "quick"
            ? { label: "다음: 유사과제 확인", to: idea.precheck ? "/new/precheck" : null, reason: idea.precheck ? null : "네 칸으로 나눈 뒤 넘어갈 수 있습니다" }
            : { label: "다음: 유사과제 확인", formId: "idea-form", busy: precheck.isPending, reason: precheck.isPending ? "유사과제를 찾는 중입니다" : null }
        }
      />
    </div>
  );
}
