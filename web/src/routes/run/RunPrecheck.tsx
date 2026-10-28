import * as React from "react";
import { Info } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useRunContext } from "./useRunContext";
import { useRunInputs } from "@/api/hooks-format";
import { differentiate, precheck } from "@/api/endpoints";
import type { ProposalRequest } from "@/api/types";
import { AlertsTable } from "@/features/idea/AlertsTable";
import { RelatedResearchList } from "@/features/idea/RelatedResearchList";
import { DifferentiationPanel } from "@/features/idea/DifferentiationPanel";
import { ChangeDialog } from "@/features/regenerate/ChangeDialog";
import { useRunChangeSave } from "@/features/regenerate/useRunChangeSave";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { changeBlockedReason } from "@/lib/runSteps";
import { SLOT_MAX } from "@/lib/validation";

/** 단계 표시 ② 를 run 안에서 열었을 때 — 이 run 의 입력으로 유사과제를 다시 보고, 차별화 방향·정책
 *  근거를 고쳐 저장한다 (항목 17). 유사과제 판정 표·관련 연구는 읽기 전용이다. */
export default function RunPrecheck() {
  const { run } = useRunContext();
  const id = run.run_id;
  const inputs = useRunInputs(id);
  const saved = inputs.data?.request;
  const [draft, setDraft] = React.useState<Pick<ProposalRequest, "differentiation" | "policy_basis"> | null>(null);
  const change = useRunChangeSave(id, run.draft_version || null);
  const blocked = changeBlockedReason(run);

  React.useEffect(() => {
    if (saved && draft === null) setDraft({ differentiation: saved.differentiation ?? "", policy_basis: saved.policy_basis ?? "" });
  }, [saved, draft]);

  const pre = useQuery({
    queryKey: ["run", id, "precheck", saved],
    queryFn: () => precheck(saved as ProposalRequest),
    enabled: !!saved,
    staleTime: Infinity,
    retry: false,
  });
  const diffM = useMutation({ mutationFn: () => differentiate(saved as ProposalRequest) });
  const diff = diffM.data?.differentiation ?? pre.data?.differentiation;

  const save = () => {
    if (!saved || !draft) return;
    void change.save({ ...saved, ...draft }, null);
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">② 유사과제 확인 (이 제안서의 입력)</h2>
        <p className="text-sm text-muted-foreground">초안을 만든 입력으로 유사과제를 다시 확인합니다. 차별화 방향·정책 근거를 고쳐 저장하면 관련 섹션만 또는 초안 전체를 새 버전으로 다시 쓸 수 있습니다.</p>
      </div>
      {blocked && (
        <Alert variant="info" role="status">
          <Info aria-hidden="true" />
          <div>
            <AlertTitle>보기 전용</AlertTitle>
            <AlertDescription>{blocked}</AlertDescription>
          </div>
        </Alert>
      )}
      <ProblemBanner error={inputs.error} onRetry={() => inputs.refetch()} />
      <section aria-labelledby="rp-alerts" className="space-y-2">
        <h3 id="rp-alerts" className="text-base font-semibold">
          유사과제 {pre.data ? `${pre.data.alerts.length}건` : ""}
        </h3>
        {pre.isPending && saved && <SkeletonBlock lines={4} />}
        <ProblemBanner error={pre.error} onRetry={() => pre.refetch()} />
        {pre.data && <AlertsTable alerts={pre.data.alerts} />}
        {pre.data?.related_research && pre.data.related_research.length > 0 && <RelatedResearchList items={pre.data.related_research} />}
      </section>

      {draft && (
        <fieldset disabled={!!blocked} className="min-w-0 space-y-4 rounded-lg border p-4">
          <legend className="px-1 font-semibold">바꿀 수 있는 입력</legend>
          <DifferentiationPanel
            diff={diff}
            loading={diffM.isPending}
            onRequest={() => diffM.mutate()}
            onPick={(text) => setDraft((d) => (d ? { ...d, differentiation: text } : d))}
            picked={draft.differentiation ?? ""}
          />
          <ProblemBanner error={diffM.error} />
          <div className="space-y-1.5">
            <Label htmlFor="rp-diff">차별화 방향</Label>
            <Textarea id="rp-diff" rows={3} maxLength={SLOT_MAX} value={draft.differentiation ?? ""} onChange={(e) => setDraft({ ...draft, differentiation: e.target.value })} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="rp-policy">정책 근거</Label>
            <Textarea id="rp-policy" rows={3} maxLength={SLOT_MAX} value={draft.policy_basis ?? ""} onChange={(e) => setDraft({ ...draft, policy_basis: e.target.value })} />
            <p className="text-xs text-muted-foreground">정책적 중요도의 유일한 근거 — 아는 정책·계획명과 요지.</p>
          </div>
          <ProblemBanner error={change.previewError} />
          <div className="flex justify-end">
            <Button type="button" onClick={save} disabled={change.previewing}>
              {change.previewing ? "바뀐 내용 확인 중…" : "입력 저장"}
            </Button>
          </div>
        </fieldset>
      )}
      <ChangeDialog
        {...change.dialog}
        onViewOnly={() => {
          if (saved) setDraft({ differentiation: saved.differentiation ?? "", policy_basis: saved.policy_basis ?? "" });
          change.dialog.onViewOnly();
        }}
      />
    </div>
  );
}
