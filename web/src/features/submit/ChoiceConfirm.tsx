import * as React from "react";
import type { CheckChoiceRow } from "@/api/types";
import { confirmBody, useConfirmChoices } from "@/api/hooks-format";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { ProblemBanner } from "@/components/ProblemBanner";
import { useToast } from "@/components/ui/toast";

const labelsOf = (row: CheckChoiceRow, ids: string[]) =>
  ids.map((i) => row.options.find((o) => o.id === i)?.label ?? "알 수 없는 선택지").join(", ");

/** 제출 전 점검의 선택형 한 줄 — AI 제안값을 그대로 확정하거나 이 자리에서 직접 고른다 (항목 16). */
function ChoiceRow({ row, runId, onDone }: { row: CheckChoiceRow; runId: string; onDone: () => void }) {
  const confirm = useConfirmChoices(runId);
  const { toast } = useToast();
  const [editing, setEditing] = React.useState(false);
  const [picked, setPicked] = React.useState<string[]>(row.confirmed.length ? row.confirmed : row.proposed);
  const single = row.key === "task_type";
  const uid = React.useId();
  const fits = (ids: string[]) => ids.length >= row.min && ids.length <= row.max;

  const send = async (ids: string[]) => {
    try {
      await confirm.mutateAsync(confirmBody(row.key, ids));
      toast(`${row.title}: ${labelsOf(row, ids)} 로 확정했습니다.`, "success");
      setEditing(false);
      onDone();
    } catch {
      /* 배너 */
    }
  };

  if (row.options.length === 0) {
    return (
      <li className="text-sm text-muted-foreground">
        <span className="font-medium text-foreground">{row.title}</span> — 선택지 목록이 비어 있어 빈칸으로 나갑니다.
      </li>
    );
  }
  const confirmed = row.confirmed.length > 0;
  return (
    <li className="space-y-2 rounded-md border bg-card p-2 text-sm">
      <p className="break-words">
        <span className="font-medium">{row.title}</span>{" "}
        {confirmed ? (
          <span className="text-muted-foreground">확정: {labelsOf(row, row.confirmed)}</span>
        ) : row.proposed.length ? (
          <span className="text-muted-foreground">AI 제안값: {labelsOf(row, row.proposed)} (미확정)</span>
        ) : (
          <span className="text-muted-foreground">제안값 없음 (미확정)</span>
        )}
      </p>
      <div className="flex flex-wrap gap-2">
        {!confirmed && row.proposed.length > 0 && (
          <Button type="button" size="sm" onClick={() => void send(row.proposed)} disabled={confirm.isPending || !fits(row.proposed)}>
            제안값 그대로 확정
          </Button>
        )}
        <Button type="button" size="sm" variant="outline" aria-expanded={editing} aria-controls={`${uid}-pick`} onClick={() => setEditing((v) => !v)}>
          {confirmed ? "다시 고르기" : "직접 고르기"}
        </Button>
      </div>
      {editing && (
        <fieldset id={`${uid}-pick`} className="space-y-2">
          <legend className="text-xs text-muted-foreground">
            {row.title} — {single ? "하나를 고르십시오" : `${row.min}~${row.max}개를 고르십시오`}
          </legend>
          <div className="grid gap-1 sm:grid-cols-2">
            {row.options.map((o) =>
              single ? (
                <Label key={o.id} className="flex items-center gap-1.5 font-normal">
                  <input type="radio" name={`${uid}-r`} checked={picked[0] === o.id} onChange={() => setPicked([o.id])} className="size-4 accent-primary" />
                  {o.label}
                </Label>
              ) : (
                <Label key={o.id} className="flex items-start gap-1.5 font-normal leading-snug">
                  <Checkbox checked={picked.includes(o.id)} onChange={(e) => setPicked(e.target.checked ? [...picked, o.id] : picked.filter((x) => x !== o.id))} className="mt-0.5" />
                  {o.label}
                </Label>
              ),
            )}
          </div>
          <Button type="button" size="sm" onClick={() => void send(picked)} disabled={confirm.isPending || !fits(picked)}>
            고른 값으로 확정
          </Button>
        </fieldset>
      )}
      <ProblemBanner error={confirm.error} />
    </li>
  );
}

export function ChoiceConfirm({ rows, runId, onDone }: { rows: CheckChoiceRow[]; runId: string; onDone: () => void }) {
  if (rows.length === 0) return null;
  return (
    <ul className="mt-2 space-y-2" aria-label="선택형 항목">
      {rows.map((r) => (
        <ChoiceRow key={r.key} row={r} runId={runId} onDone={onDone} />
      ))}
    </ul>
  );
}
