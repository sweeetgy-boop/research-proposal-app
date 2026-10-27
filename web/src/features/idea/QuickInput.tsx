import * as React from "react";
import { useMutation } from "@tanstack/react-query";
import { Sparkles, Wand2 } from "lucide-react";
import { mergeStructure, structureIdea } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import type { StructureField, StructureOut } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ProblemBanner } from "@/components/ProblemBanner";
import { UntrustedText } from "@/components/UntrustedText";
import { SLOT_MAX, SHORT_MAX } from "@/lib/validation";
import { cn } from "@/lib/utils";

export const QUICK_MAX = 2000;
const FIELDS: StructureField[] = ["current_state", "root_cause", "limitation", "goal"];

export interface QuickInputProps {
  text: string;
  title: string;
  onTextChange: (v: string) => void;
  onTitleChange: (v: string) => void;
  /** 4칸을 상세 입력에 채우고 상세 모드로 넘어간다 */
  onFilled: (fields: Record<StructureField, string>, title: string) => void;
  /** 503(기능 꺼짐·LLM 없음) — 상세 입력으로 되돌린다 */
  onUnavailable: () => void;
}

/** U2 간편 입력 — 한두 문장(+가제) → 4칸 미리보기 → 보완 질문(0~4) → 답 합치기 → 상세 입력에 채우기.
 *  칸 글은 모델 출력(비신뢰) → UntrustedText. 서버는 자유 문장을 저장하지 않는다. */
export function QuickInput({ text, title, onTextChange, onTitleChange, onFilled, onUnavailable }: QuickInputProps) {
  const [result, setResult] = React.useState<StructureOut | null>(null);
  const [answers, setAnswers] = React.useState<Record<string, string>>({});
  const previewRef = React.useRef<HTMLDivElement>(null);

  const structure = useMutation({
    mutationFn: () => structureIdea(text.trim(), title.trim()),
    onSuccess: (out) => {
      setResult(out);
      setAnswers({});
      window.setTimeout(() => previewRef.current?.focus(), 0);
    },
    onError: (e) => {
      if (isApiError(e) && e.status === 503) onUnavailable();
    },
  });
  const merge = useMutation({
    mutationFn: () => mergeStructure({ fields: result?.fields ?? {}, answers }),
    onSuccess: (out) => {
      setResult(out);
      setAnswers({});
    },
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;
    structure.mutate();
  };
  const unavailable = isApiError(structure.error) && structure.error.status === 503;
  const answered = Object.values(answers).some((v) => v.trim());

  return (
    <div className="space-y-6">
      <form onSubmit={submit} noValidate className="space-y-4 rounded-lg border p-4">
        <div className="space-y-1.5">
          <div className="flex items-baseline justify-between gap-2">
            <Label htmlFor="quick-text">
              아이디어를 한두 문장으로<span className="ml-1 text-destructive" aria-hidden="true">*</span>
              <span className="sr-only"> (필수)</span>
            </Label>
            <span className={cn("text-xs tabular-nums text-muted-foreground", text.length > QUICK_MAX && "text-destructive")} aria-hidden="true">
              {text.length}/{QUICK_MAX}
            </span>
          </div>
          <p id="quick-text-hint" className="text-xs text-muted-foreground">
            무엇이 문제이고 무엇을 하고 싶은지만 적으면 됩니다. 로컬 모델이 네 칸(현황·원인·한계·목표)으로 나누고, 모자란 칸은 질문합니다. 이 문장은 서버에 저장되지 않습니다.
          </p>
          <Textarea id="quick-text" rows={3} value={text} maxLength={QUICK_MAX} onChange={(e) => onTextChange(e.target.value)} aria-describedby="quick-text-hint" aria-required />
        </div>
        <div className="space-y-1.5 sm:max-w-md">
          <Label htmlFor="quick-title">가제 (선택)</Label>
          <Input id="quick-title" value={title} maxLength={SHORT_MAX} onChange={(e) => onTitleChange(e.target.value)} />
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="submit" disabled={!text.trim() || structure.isPending}>
            <Wand2 aria-hidden="true" />
            {structure.isPending ? "나누는 중…" : "네 칸으로 나누기"}
          </Button>
        </div>
      </form>

      {unavailable ? (
        <Alert variant="info">
          <Sparkles aria-hidden="true" />
          <div>
            <AlertTitle>간편 입력을 쓸 수 없습니다</AlertTitle>
            <AlertDescription>로컬 모델이 없거나 기능이 꺼져 있습니다. 상세 입력(4칸)으로 바꿉니다.</AlertDescription>
          </div>
        </Alert>
      ) : (
        <ProblemBanner error={structure.error} onRetry={() => structure.mutate()} />
      )}
      <ProblemBanner error={merge.error} />

      {result && (
        <section ref={previewRef} tabIndex={-1} aria-labelledby="quick-preview-h" className="space-y-4 rounded-lg border p-4">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id="quick-preview-h" className="text-lg font-semibold">네 칸 미리보기</h2>
            {result.complete ? <Badge variant="success">모두 채워짐</Badge> : <Badge variant="warning">빈 칸 {result.questions.length}개</Badge>}
            {result.model && <Badge variant="outline">{result.provider ?? "—"} / {result.model}</Badge>}
          </div>
          {result.parse_failed && (
            <p role="status" className="text-sm text-warning">
              모델 응답을 해석하지 못해 칸이 비어 있습니다. 아래 질문에 답하거나 상세 입력에서 직접 채우십시오.
            </p>
          )}
          <dl className="grid gap-3 sm:grid-cols-2">
            {FIELDS.map((k) => (
              <div key={k} className="rounded-md border p-3">
                <dt className="text-xs font-medium text-muted-foreground">{result.labels[k] ?? k}</dt>
                <dd className="mt-1 text-sm">{result.fields[k] ? <UntrustedText text={result.fields[k]} /> : <span className="text-muted-foreground">(비어 있음 — 질문으로 채웁니다)</span>}</dd>
              </div>
            ))}
          </dl>

          {result.questions.length > 0 && (
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                if (answered) merge.mutate();
              }}
            >
              <h3 className="text-base font-semibold">보완 질문 {result.questions.length}개</h3>
              {result.questions.map((q) => (
                <div key={q.field} className="space-y-1">
                  <Label htmlFor={`qa-${q.field}`}>
                    <span className="text-xs text-muted-foreground">[{q.label}] </span>
                    {q.question}
                  </Label>
                  <Textarea id={`qa-${q.field}`} rows={2} maxLength={SLOT_MAX} value={answers[q.field] ?? ""} onChange={(e) => setAnswers((s) => ({ ...s, [q.field]: e.target.value }))} />
                </div>
              ))}
              <div className="flex flex-wrap justify-end gap-2">
                <Button type="submit" variant="secondary" disabled={!answered || merge.isPending}>
                  {merge.isPending ? "합치는 중…" : "답 반영"}
                </Button>
              </div>
            </form>
          )}

          <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
            <p className="text-xs text-muted-foreground">
              {result.skip_allowed && result.questions.length > 0 ? "질문은 건너뛸 수 있습니다 — 빈 칸은 상세 입력에서 직접 채웁니다." : "확인하면 네 칸이 상세 입력에 채워지고 고칠 수 있습니다."}
            </p>
            <Button type="button" onClick={() => onFilled(result.fields, title.trim())}>
              {result.questions.length > 0 && result.skip_allowed ? "건너뛰고 상세 입력에 채우기" : "확인하고 상세 입력에 채우기"}
            </Button>
          </div>
        </section>
      )}
    </div>
  );
}
