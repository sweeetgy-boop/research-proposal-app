/** 초안이 있는 run 에서 ①·② 입력을 저장할 때 (항목 17):
 *  미리보기(바뀐 칸·관련 섹션) → 바뀐 것이 있으면 세 가지 선택 대화상자 → 다시 쓰기(새 버전).
 *  레인 A·B 의 ①·② 화면도 이 훅과 <ChangeDialog {...dialog} /> 를 그대로 쓰면 같은 흐름이 된다. */
import * as React from "react";
import { useNavigate } from "react-router";
import { usePreviewRequestChange, useRegenerate } from "@/api/hooks-format";
import type { ProposalRequest, RegenerateMode, RequestPreviewOut } from "@/api/types";
import { useToast } from "@/components/ui/toast";
import type { ChangeDialogProps } from "./ChangeDialog";

export function useRunChangeSave(runId: string, baseVersion: number | null) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const preview = usePreviewRequestChange(runId);
  const regen = useRegenerate(runId);
  const [pending, setPending] = React.useState<{ request: ProposalRequest; priority: string[] | null; out: RequestPreviewOut } | null>(null);

  const save = async (request: ProposalRequest, priority: string[] | null = null): Promise<void> => {
    try {
      const out = await preview.mutateAsync({ request, priority_evidence: priority });
      if (out.fields.length === 0) {
        toast("바뀐 내용이 없습니다.");
        return;
      }
      regen.reset();
      setPending({ request, priority, out });
    } catch {
      /* preview.error 를 화면이 보여 준다 */
    }
  };

  const close = () => setPending(null);

  const viewOnly = () => {
    setPending(null);
    navigate(`/runs/${runId}/draft`);
  };

  const run = async (mode: RegenerateMode) => {
    if (!pending) return;
    try {
      const out = await regen.mutateAsync({
        request: pending.request,
        priority_evidence: pending.priority,
        mode,
        base_version: baseVersion,
      });
      setPending(null);
      if (out.saved_only) {
        toast("입력만 저장했습니다 — 다시 쓸 섹션이 없습니다(양식 칸에만 들어가는 값).", "success");
      } else {
        const done = out.regenerated.map((s) => s.title).join(", ");
        const kept = out.failed.length ? ` · 이전 내용 유지: ${out.failed.map((s) => s.title).join(", ")}` : "";
        toast(`새 버전 v${out.version}: ${done} 다시 씀${kept}`, out.failed.length ? "info" : "success");
      }
      navigate(`/runs/${runId}/draft`);
    } catch {
      /* regen.error 를 대화상자가 보여 준다 */
    }
  };

  const dialog: ChangeDialogProps = {
    open: pending !== null,
    preview: pending?.out ?? null,
    busy: regen.isPending,
    error: regen.error,
    onClose: close,
    onViewOnly: viewOnly,
    onRegenerate: (mode) => void run(mode),
  };
  return { save, previewing: preview.isPending, previewError: preview.error, dialog };
}
