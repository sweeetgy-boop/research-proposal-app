import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { runPolicyCards, runPolicyChoice, runPolicyPolish } from "@/api/editai";
import { keys } from "@/api/hooks";
import type { PolicyChoice } from "@/api/types";
import { Dialog } from "@/components/ui/dialog";
import { ProblemBanner } from "@/components/ProblemBanner";
import { PolicyCards } from "./PolicyCards";

/** ④ 빈 2-가-(1) 정책적 중요도 — 같은 작성안 4개에서 고르면 새 버전(note "정책 근거 선택"). */
export function RunPolicyDialog({
  runId,
  open,
  baseVersion,
  disabled,
  onClose,
  onApplied,
}: {
  runId: string;
  open: boolean;
  baseVersion: number;
  disabled?: boolean;
  onClose: () => void;
  onApplied: (version: number) => void;
}) {
  const qc = useQueryClient();
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<unknown>(null);
  const [value, setValue] = React.useState<PolicyChoice | null>(null);

  const choose = async (choice: PolicyChoice) => {
    setValue(choice);
    if (disabled) return;
    setBusy(true);
    setError(null);
    try {
      const v = await runPolicyChoice(runId, choice, baseVersion);
      await qc.invalidateQueries({ queryKey: keys.run(runId) });
      onApplied(v.version);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} title="정책 근거 고르기 — 2-가-(1) 정책적 중요도" className="w-[min(96vw,60rem)]">
      {disabled && <p className="mb-2 text-sm text-muted-foreground">저장하지 않은 편집이 있어 고를 수 없습니다 (작성안은 볼 수 있습니다).</p>}
      <ProblemBanner error={error} className="mb-3" />
      {open && (
        <PolicyCards
          load={(exclude, signal) => runPolicyCards(runId, exclude, signal)}
          polish={(choice, text, signal) => runPolicyPolish(runId, choice, text, signal)}
          value={value}
          onChoose={choose}
          busy={busy || disabled}
        />
      )}
    </Dialog>
  );
}
