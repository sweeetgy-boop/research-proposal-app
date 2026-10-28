import * as React from "react";
import { Sparkles } from "lucide-react";
import type { PlanField, PrecheckRequest } from "@/api/types";
import { PLAN_FIELDS } from "@/api/types";
import { polishField } from "@/api/endpoints-precheck";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ProblemBanner } from "@/components/ProblemBanner";
import { UntrustedText } from "@/components/UntrustedText";
import { changedFields } from "./model";

/** 과제안 직접 고치기 — 칸마다 고치고 [AI로 다듬기](그 칸만, Argon → 로컬). 원래 아이디어와 나란히 본다. */
export function PlanEditor({
  request,
  initial,
  original,
  onConfirm,
  onCancel,
}: {
  request: PrecheckRequest;
  initial: Record<PlanField, string>;
  original: Record<PlanField, string>;
  onConfirm: (fields: Record<PlanField, string>) => void;
  onCancel: () => void;
}) {
  const [fields, setFields] = React.useState(initial);
  const [busy, setBusy] = React.useState<PlanField | null>(null);
  const [notes, setNotes] = React.useState<Partial<Record<PlanField, string>>>({});
  const [error, setError] = React.useState<unknown>(null);

  const polish = async (key: PlanField) => {
    setBusy(key);
    setError(null);
    try {
      const out = await polishField(request, key, fields[key] ?? "");
      setFields((f) => ({ ...f, [key]: out.text }));
      setNotes((n) => ({
        ...n,
        [key]: out.changed ? `${out.by_label ?? "AI"} 가 다듬었습니다.` : (out.reason ?? "바뀐 내용이 없습니다."),
      }));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  const changed = changedFields(original, fields);
  const empty = !fields.goal.trim();
  return (
    <section className="space-y-3 rounded-lg border p-4" aria-labelledby="plan-editor-title">
      <h3 id="plan-editor-title" className="text-base font-semibold">
        과제안 직접 작성·수정
      </h3>
      <p className="text-sm text-muted-foreground">칸마다 고치고, 필요하면 [AI로 다듬기] 로 그 칸만 다듬으십시오. 오른쪽은 원래 아이디어입니다.</p>
      <ProblemBanner error={error} />
      {PLAN_FIELDS.map((f) => {
        const id = `plan-${f.key}`;
        return (
          <div key={f.key} className="grid gap-2 md:grid-cols-2">
            <div className="space-y-1">
              <div className="flex items-center justify-between gap-2">
                <Label htmlFor={id}>{f.label}</Label>
                <Button size="sm" variant="ghost" onClick={() => polish(f.key)} disabled={busy !== null || !(fields[f.key] ?? "").trim()}>
                  <Sparkles aria-hidden="true" />
                  {busy === f.key ? "다듬는 중…" : `${f.label} AI로 다듬기`}
                </Button>
              </div>
              <Textarea
                id={id}
                rows={f.short ? 2 : 3}
                value={fields[f.key] ?? ""}
                onChange={(e) => setFields((v) => ({ ...v, [f.key]: e.target.value }))}
              />
              {notes[f.key] && (
                <p role="status" className="text-xs text-muted-foreground">
                  {notes[f.key]}
                </p>
              )}
            </div>
            <div className="rounded-md bg-muted/40 p-2 text-sm">
              <p className="text-xs text-muted-foreground">원래 아이디어</p>
              <UntrustedText as="p" text={original[f.key] || "(비어 있음)"} />
            </div>
          </div>
        );
      })}
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => onConfirm(fields)} disabled={empty}>
          이 내용으로 확정
        </Button>
        <Button variant="outline" onClick={onCancel}>
          취소
        </Button>
        <span className="text-xs text-muted-foreground">
          {empty ? "연구목표는 비울 수 없습니다." : changed.length ? `원래 아이디어와 다른 칸 ${changed.length}개` : "원래 아이디어와 같습니다."}
        </span>
      </div>
    </section>
  );
}
