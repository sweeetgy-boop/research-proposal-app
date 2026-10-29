import * as React from "react";
import type { ProposalRequest } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { FIELD_LABELS, SHORT_MAX, SLOT_MAX, summarizeErrors, validateRequest, type FieldErrors } from "@/lib/validation";
import { cn } from "@/lib/utils";

interface FieldProps {
  name: keyof ProposalRequest & string;
  value: string;
  onChange: (v: string) => void;
  error?: string;
  required?: boolean;
  max: number;
  hint?: string;
  short?: boolean;
  rows?: number;
}

function Field({ name, value, onChange, error, required, max, hint, short, rows = 3 }: FieldProps) {
  const id = `f-${name}`;
  const describedBy = [hint ? `${id}-hint` : null, error ? `${id}-err` : null].filter(Boolean).join(" ") || undefined;
  const over = value.length > max;
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <Label htmlFor={id}>
          {FIELD_LABELS[name]}
          {required && (
            <span className="ml-1 text-destructive" aria-hidden="true">
              *
            </span>
          )}
          {required && <span className="sr-only"> (필수)</span>}
        </Label>
        <span className={cn("text-xs tabular-nums text-muted-foreground", over && "text-destructive")} aria-hidden="true">
          {value.length}/{max}
        </span>
      </div>
      {hint && (
        <p id={`${id}-hint`} className="text-xs text-muted-foreground">
          {hint}
        </p>
      )}
      {short ? (
        <Input id={id} value={value} onChange={(e) => onChange(e.target.value)} aria-invalid={!!error} aria-describedby={describedBy} aria-required={required} />
      ) : (
        <Textarea id={id} rows={rows} value={value} onChange={(e) => onChange(e.target.value)} aria-invalid={!!error} aria-describedby={describedBy} aria-required={required} />
      )}
      <p id={`${id}-err`} className="min-h-5 text-sm text-destructive" aria-live="polite">
        {error ?? ""}
      </p>
    </div>
  );
}

export function IdeaForm({
  value,
  onChange,
  onSubmit,
  busy,
  submitLabel = "유사과제 확인",
  hideSubmit = false,
  policyTools,
}: {
  value: ProposalRequest;
  onChange: (patch: Partial<ProposalRequest>) => void;
  onSubmit: (req: ProposalRequest) => void;
  busy?: boolean;
  submitLabel?: string;
  /** 아래 이동 막대가 [다음: 유사과제 확인] 으로 이 폼을 제출할 때 (id="idea-form") — 폼 안 단추는 숨긴다 */
  hideSubmit?: boolean;
  /** 정책 근거 칸 아래 — [정책 근거 추천 열기]·안내 (ADR 0052) */
  policyTools?: React.ReactNode;
}) {
  const [errors, setErrors] = React.useState<FieldErrors>({});
  const [touched, setTouched] = React.useState(false);
  const summaryRef = React.useRef<HTMLDivElement>(null);
  const live = touched ? validateRequest(value) : errors;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const errs = validateRequest(value);
    setErrors(errs);
    setTouched(true);
    if (Object.keys(errs).length) {
      summaryRef.current?.focus();
      return;
    }
    onSubmit(value);
  };

  const set = (k: keyof ProposalRequest) => (v: string) => onChange({ [k]: v } as Partial<ProposalRequest>);
  const summary = summarizeErrors(live);

  return (
    <form id="idea-form" onSubmit={submit} noValidate className="space-y-6">
      <div ref={summaryRef} tabIndex={-1} className="min-h-6" aria-live="assertive">
        {summary && touched && (
          <p role="alert" className="rounded-md border border-destructive/40 bg-destructive-soft p-3 text-sm text-destructive-soft-foreground">
            {summary}
          </p>
        )}
      </div>

      <fieldset className="space-y-4">
        <legend className="text-base font-semibold">필수 입력</legend>
        <Field name="current_state" value={value.current_state} onChange={set("current_state")} error={live.current_state} required max={SLOT_MAX} hint="지금 현장에서 무엇이 문제인가" />
        <Field name="root_cause" value={value.root_cause} onChange={set("root_cause")} error={live.root_cause} required max={SLOT_MAX} hint="왜 그 문제가 생기는가" />
        <Field name="limitation" value={value.limitation} onChange={set("limitation")} error={live.limitation} required max={SLOT_MAX} hint="지금 방식으로는 왜 해결되지 않는가" />
        <Field name="goal" value={value.goal} onChange={set("goal")} error={live.goal} required max={SLOT_MAX} hint="연구로 무엇을 이루려는가" />
      </fieldset>

      {/* 정책 근거는 접지 않는다 — 비면 2-가-(1) 이 빈칸으로 생성되므로 늘 보이게 (ADR 0052) */}
      <div className="space-y-2 rounded-lg border bg-card p-4" data-testid="policy-basis-box">
        <Field name="policy_basis" value={value.policy_basis ?? ""} onChange={set("policy_basis")} error={live.policy_basis} max={SLOT_MAX} hint="2-가-(1) 정책적 중요도의 유일한 근거 — 아는 정책·계획명과 요지. 비면 그 칸은 빈칸으로 생성될 수 있습니다" />
        {policyTools}
      </div>

      <details className="rounded-lg border bg-card p-4" open={!!(value.title_hint || value.differentiation)}>
        <summary className="cursor-pointer font-semibold">선택 입력 (가제·제약·부서·예산)</summary>
        <div className="mt-4 space-y-4">
          <Field name="title_hint" value={value.title_hint ?? ""} onChange={set("title_hint")} error={live.title_hint} max={SHORT_MAX} short hint="있으면 과제명을 이것으로 다듬습니다" />
          <Field name="constraints" value={value.constraints ?? ""} onChange={set("constraints")} error={live.constraints} max={SLOT_MAX} rows={2} />
          <Field name="beneficiaries" value={value.beneficiaries ?? ""} onChange={set("beneficiaries")} error={live.beneficiaries} max={SLOT_MAX} rows={2} hint="차량처·시설처 등" />
          <Field name="remarks" value={value.remarks ?? ""} onChange={set("remarks")} error={live.remarks} max={SLOT_MAX} rows={2} />
          <Field name="differentiation" value={value.differentiation ?? ""} onChange={set("differentiation")} error={live.differentiation} max={SLOT_MAX} rows={2} hint="유사과제 확인 뒤 제안을 고르거나 직접 적습니다" />
          <Field name="department" value={value.department ?? ""} onChange={set("department")} error={live.department} max={SHORT_MAX} short hint="양식 칸에만 쓰입니다" />
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="f-budget-account">{FIELD_LABELS["budget.account"]}</Label>
              <Input
                id="f-budget-account"
                value={value.budget?.account ?? ""}
                onChange={(e) => onChange({ budget: { account: e.target.value, amount_thousand_krw: value.budget?.amount_thousand_krw ?? null } })}
                aria-invalid={!!live["budget.account"]}
              />
              <p className="min-h-5 text-sm text-destructive">{live["budget.account"] ?? ""}</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="f-budget-amount">{FIELD_LABELS["budget.amount_thousand_krw"]}</Label>
              <Input
                id="f-budget-amount"
                type="number"
                inputMode="numeric"
                min={0}
                step={1}
                value={value.budget?.amount_thousand_krw ?? ""}
                onChange={(e) =>
                  onChange({
                    budget: {
                      account: value.budget?.account ?? "",
                      amount_thousand_krw: e.target.value === "" ? null : Number(e.target.value),
                    },
                  })
                }
                aria-invalid={!!live["budget.amount_thousand_krw"]}
              />
              <p className="min-h-5 text-sm text-destructive">{live["budget.amount_thousand_krw"] ?? ""}</p>
            </div>
          </div>
        </div>
      </details>

      {!hideSubmit && (
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="submit" disabled={busy}>
            {busy ? "확인 중…" : submitLabel}
          </Button>
        </div>
      )}
    </form>
  );
}
