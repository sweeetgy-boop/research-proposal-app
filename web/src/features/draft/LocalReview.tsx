import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Check, ShieldCheck, X } from "lucide-react";
import { applyLocalSuggestion, dismissLocalSuggestion, retryLocalSuggestion } from "@/api/localReview";
import { keys } from "@/api/hooks";
import { isApiError } from "@/api/client";
import type { LocalReviewView, LocalSuggestion, LocalVerdict } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { UntrustedText } from "@/components/UntrustedText";
import { AiCancelledNote, AiWaiting } from "@/components/AiWaiting";
import { ProblemBanner } from "@/components/ProblemBanner";
import { useToast } from "@/components/ui/toast";
import { useAiCall } from "@/lib/useAiCall";

const VERDICT_VARIANT: Record<LocalVerdict, "success" | "info" | "warning"> = { 지지: "success", 부분: "info", 불일치: "warning" };

/** 문장 옆 "로컬 검토: 지지 / 부분 / 불일치" (L2, ADR 0040) — 로컬 모델이 근거와 대조한 판정 */
export function LocalVerdictBadge({ verdict }: { verdict: LocalVerdict | undefined }) {
  if (!verdict) return null;
  return (
    <Badge variant={VERDICT_VARIANT[verdict] ?? "outline"} data-testid="local-verdict">
      <ShieldCheck className="mr-1 size-3" aria-hidden="true" />
      로컬 검토: {verdict}
    </Badge>
  );
}

/** 불일치 문장의 Argon 제안 — "근거 안에서 다시 쓰기 또는 빼기". 자동 반영 없음:
 *  [반영] = 보통 편집 경로로 새 버전, [무시] = 결정만 기록(버전 그대로). 실패면 사유 + [다시 시도]. */
export function LocalSuggestionCard({
  runId,
  suggestion,
  baseVersion,
  disabled,
  disabledReason,
}: {
  runId: string;
  suggestion: LocalSuggestion;
  baseVersion: number;
  /** 현재 버전이 아니거나 저장하지 않은 편집이 있을 때 */
  disabled?: boolean;
  disabledReason?: string;
}) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<unknown>(null);
  const retry = useAiCall((_: void, signal) => retryLocalSuggestion(runId, suggestion.id, signal));
  const refresh = () => qc.invalidateQueries({ queryKey: keys.run(runId) });

  const apply = async () => {
    setBusy(true);
    setError(null);
    try {
      const out = await applyLocalSuggestion(runId, suggestion.id, baseVersion);
      toast(out.version === baseVersion ? "바뀐 내용이 없어 새 버전을 만들지 않았습니다." : `로컬 검토 제안을 v${out.version} 으로 반영했습니다.`, "success");
      await refresh();
    } catch (e) {
      setError(e);
      if (isApiError(e) && e.status === 409) await refresh();
    } finally {
      setBusy(false);
    }
  };
  const dismiss = async () => {
    setBusy(true);
    setError(null);
    try {
      await dismissLocalSuggestion(runId, suggestion.id);
      toast("무시로 기록했습니다 (새 버전 없음).", "success");
      await refresh();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  const again = async () => {
    const out = await retry.run(undefined);
    if (out) await refresh();
  };

  const status = suggestion.status;
  return (
    <div className="mt-1 space-y-1.5 rounded-md border border-warning/50 bg-warning/5 p-2 text-sm" data-testid="local-suggestion" aria-label="로컬 검토 제안">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant="outline">Argon 제안</Badge>
        {suggestion.action_label && <span className="font-medium">{suggestion.action_label}</span>}
        {status !== "open" && <Badge variant={status === "applied" ? "success" : status === "dismissed" ? "secondary" : "destructive"}>{suggestion.status_label}</Badge>}
        {suggestion.filtered && <span className="text-xs text-muted-foreground">(다시 쓴 문장이 근거 밖 내용이라 걸러져 빼기로 제안)</span>}
      </div>
      {status === "failed" ? (
        <p className="text-muted-foreground">
          제안을 받지 못했습니다 — {suggestion.reason_label || "호출 실패"}.
        </p>
      ) : suggestion.action === "rewrite" ? (
        <p className="rounded bg-background p-1.5">
          <UntrustedText text={suggestion.text} className="diff-ins" />
        </p>
      ) : (
        <p className="text-muted-foreground">근거로 받칠 수 없어 이 문장을 빼자는 제안입니다.</p>
      )}
      {suggestion.reason && status !== "failed" && (
        <p className="text-xs text-muted-foreground">
          이유: <UntrustedText text={suggestion.reason} />
        </p>
      )}
      {status === "open" && (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={apply} disabled={busy || disabled} aria-label="로컬 검토 제안 반영">
            <Check aria-hidden="true" />
            반영
          </Button>
          <Button size="sm" variant="outline" onClick={dismiss} disabled={busy || disabled} aria-label="로컬 검토 제안 무시">
            <X aria-hidden="true" />
            무시
          </Button>
          {disabled && disabledReason && <span className="text-xs text-muted-foreground">{disabledReason}</span>}
        </div>
      )}
      {status === "failed" && (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" onClick={again} disabled={retry.pending || disabled}>
            다시 시도
          </Button>
          <Button size="sm" variant="ghost" onClick={dismiss} disabled={busy || disabled} aria-label="로컬 검토 제안 무시">
            무시
          </Button>
        </div>
      )}
      <AiWaiting pending={retry.pending} elapsed={retry.elapsed} onCancel={retry.cancel} what="Argon 제안" />
      <AiCancelledNote show={retry.cancelled} />
      <ProblemBanner error={error ?? retry.error} />
    </div>
  );
}

/** 섹션 화면 요약 — "로컬 검토 지지 n · 부분 n · 불일치 n (미결정 n)" */
export function LocalReviewSummary({ view }: { view: LocalReviewView | null | undefined }) {
  if (!view?.enabled) return null;
  const c = view.counts ?? {};
  return (
    <p className="mb-2 flex flex-wrap items-center gap-1.5 text-sm" data-testid="local-review-summary">
      <span className="font-medium">로컬 검토</span>
      <Badge variant="success">지지 {c["지지"] ?? 0}</Badge>
      <Badge variant="info">부분 {c["부분"] ?? 0}</Badge>
      <Badge variant={(c["불일치"] ?? 0) > 0 ? "warning" : "success"}>불일치 {c["불일치"] ?? 0}</Badge>
      {(view.unresolved ?? 0) > 0 && <span className="text-muted-foreground">결정하지 않은 불일치 {view.unresolved}건</span>}
    </p>
  );
}
