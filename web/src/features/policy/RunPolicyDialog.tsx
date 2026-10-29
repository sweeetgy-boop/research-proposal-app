import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { runPolicyCards, runPolicyChoice, runPolicyPolish } from "@/api/editai";
import { keys } from "@/api/hooks";
import type { PolicyChoice } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ProblemBanner } from "@/components/ProblemBanner";
import { PolicyCards } from "./PolicyCards";
import { editedChoice, withManual } from "./model";

/** ④ 2-가-(1) 정책적 중요도 — 정책 근거 넣기·바꾸기. 작성안에서 고르거나(직접 입력이 있으면 그 뒤에 덧붙음)
 *  직접 입력만으로 반영하면 새 버전(note "정책 근거 선택"). ① 팝업의 "직접 입력" 과 같은 칸 (ADR 0052). */
export function RunPolicyDialog({
  runId,
  open,
  baseVersion,
  disabled,
  disabledReason,
  onClose,
  onApplied,
}: {
  runId: string;
  open: boolean;
  baseVersion: number;
  disabled?: boolean;
  /** 고를 수 없는 이유 (작성안은 볼 수 있다) */
  disabledReason?: string;
  onClose: () => void;
  onApplied: (version: number) => void;
}) {
  const qc = useQueryClient();
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<unknown>(null);
  const [value, setValue] = React.useState<PolicyChoice | null>(null);
  const [direct, setDirect] = React.useState("");

  React.useEffect(() => {
    if (open) setDirect("");
  }, [open]);

  const save = async (choice: PolicyChoice) => {
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
  const choose = (choice: PolicyChoice) => save(withManual(choice, direct));
  const directOnly = editedChoice(null, direct);

  return (
    <Dialog open={open} onClose={onClose} title="정책 근거 넣기·바꾸기 — 2-가-(1) 정책적 중요도" className="w-[min(96vw,60rem)]">
      {disabled && <p className="mb-2 text-sm text-muted-foreground">{disabledReason ?? "저장하지 않은 편집이 있어 고를 수 없습니다"} (작성안은 볼 수 있습니다).</p>}
      <ProblemBanner error={error} className="mb-3" />
      <div className="mb-5 space-y-1.5 rounded-lg border bg-card p-3">
        <Label htmlFor="run-policy-direct">직접 입력 (선택)</Label>
        <p id="run-policy-direct-hint" className="text-xs text-muted-foreground">
          아는 정책·계획명과 요지를 줄마다 한 문장으로 적습니다. 아래 작성안을 고르면 그 뒤에 덧붙고, 직접 입력만 반영할 수도 있습니다.
        </p>
        <Textarea id="run-policy-direct" rows={3} maxLength={2000} value={direct} onChange={(e) => setDirect(e.target.value)} aria-describedby="run-policy-direct-hint" disabled={busy} />
        <div className="flex justify-end">
          <Button size="sm" onClick={() => void save(directOnly)} disabled={busy || disabled || directOnly.sentences.length === 0}>
            {busy ? "반영 중…" : "직접 입력만 반영"}
          </Button>
        </div>
      </div>
      {open && (
        <PolicyCards
          load={(exclude, signal) => runPolicyCards(runId, exclude, signal)}
          polish={(choice, text, signal) => runPolicyPolish(runId, choice, text, signal)}
          value={value}
          onChoose={choose}
          busy={busy || disabled}
          manual={false}
        />
      )}
    </Dialog>
  );
}
