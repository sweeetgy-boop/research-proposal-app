import * as React from "react";
import { Info } from "lucide-react";
import { useRunContext } from "./useRunContext";
import { useRunInputs } from "@/api/hooks-format";
import type { ProposalRequest } from "@/api/types";
import { IdeaForm } from "@/features/idea/IdeaForm";
import { ChangeDialog } from "@/features/regenerate/ChangeDialog";
import { useRunChangeSave } from "@/features/regenerate/useRunChangeSave";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { changeBlockedReason } from "@/lib/runSteps";

/** 단계 표시 ① 을 run 안에서 열었을 때 — 그 run 의 저장된 입력을 보고 고친다 (항목 17).
 *  초안이 있으면 저장할 때 세 가지(보기만·관련 섹션만·전체 다시 생성) 중 고른다. */
export default function RunIdea() {
  const { run } = useRunContext();
  const id = run.run_id;
  const inputs = useRunInputs(id);
  const [value, setValue] = React.useState<ProposalRequest | null>(null);
  const change = useRunChangeSave(id, run.draft_version || null);
  const blocked = changeBlockedReason(run);

  React.useEffect(() => {
    if (inputs.data && value === null) setValue(inputs.data.request);
  }, [inputs.data, value]);

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div>
        <h2 className="text-lg font-semibold">① 아이디어 입력 (이 제안서의 입력)</h2>
        <p className="text-sm text-muted-foreground">초안을 만들 때 쓴 입력입니다. 고쳐 저장하면 바뀐 내용과 관련된 섹션만, 또는 초안 전체를 새 버전으로 다시 쓸 수 있습니다.</p>
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
      {inputs.isPending && <SkeletonBlock lines={6} />}
      <ProblemBanner error={inputs.error} onRetry={() => inputs.refetch()} />
      <ProblemBanner error={change.previewError} />
      {value && (
        <fieldset disabled={!!blocked} className="min-w-0">
          <legend className="sr-only">이 제안서의 아이디어 입력</legend>
          <IdeaForm
            value={value}
            onChange={(patch) => setValue((v) => (v ? { ...v, ...patch } : v))}
            onSubmit={(req) => void change.save(req, null)}
            busy={change.previewing}
            submitLabel={change.previewing ? "바뀐 내용 확인 중…" : "입력 저장"}
          />
        </fieldset>
      )}
      <ChangeDialog
        {...change.dialog}
        onViewOnly={() => {
          if (inputs.data) setValue(inputs.data.request); // 고친 내용은 버린다
          change.dialog.onViewOnly();
        }}
      />
    </div>
  );
}
