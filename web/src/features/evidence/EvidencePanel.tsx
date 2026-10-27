import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ExternalLink, ScanSearch } from "lucide-react";
import { Link } from "react-router";
import { keys, useDecideEvidence, useSentenceEvidence } from "@/api/hooks";
import { isApiError } from "@/api/client";
import type { Citation, DecisionAction, EvidenceItem, Problem_ } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { UntrustedText } from "@/components/UntrustedText";
import { EmptyState } from "@/components/EmptyState";
import { useToast } from "@/components/ui/toast";
import { SUPPORT_VARIANT } from "@/lib/sections";
import { formatDate } from "@/lib/utils";
import { cn } from "@/lib/utils";

export const EVIDENCE_ALERT_CODES = new Set(["evidence_mismatch", "evidence_all_excluded"]);
const ACTIONS: { id: DecisionAction; label: string }[] = [
  { id: "approve", label: "승인" },
  { id: "replace", label: "교체" },
  { id: "exclude", label: "제외" },
];
const DECISION_LABEL: Record<string, string> = { approve: "승인됨", replace: "교체됨", exclude: "제외됨" };

export interface EvidencePanelProps {
  runId: string;
  sentenceId: string | null;
  sentenceText?: string;
  citations: Citation[];
  /** 이 문장에 붙은 알림 (evidence_mismatch·evidence_all_excluded 등) */
  problems?: Problem_[];
  baseVersion: number;
  /** usability.yaml strategy_source=draft — 전략체계 목록이 확정 전 */
  strategyDraft?: boolean;
  onClose: () => void;
}

type Pending = Record<string, { action: DecisionAction; replacement?: string }>;

function EvidenceCard({
  item,
  pending,
  onChange,
  citations,
  disabled,
}: {
  item: EvidenceItem;
  pending: Pending[string] | undefined;
  onChange: (p: Pending[string] | null) => void;
  citations: Citation[];
  disabled: boolean;
}) {
  const action = pending?.action ?? null;
  const groupId = `ev-${item.evidence_id}`;
  const others = citations.filter((c) => c.id !== item.evidence_id);
  return (
    <li className="space-y-2 rounded-md border p-3 text-sm">
      <div className="flex flex-wrap items-center gap-1">
        <UntrustedText text={item.title ?? item.doc_id} className="font-medium" />
        <span className="font-mono text-xs text-muted-foreground">{item.evidence_id}</span>
      </div>
      <div className="flex flex-wrap items-center gap-1 text-xs">
        <Badge variant="secondary">{item.source_label}</Badge>
        {item.orgs.length > 0 && <span className="text-muted-foreground">{item.orgs.join(", ")}</span>}
        <span className="text-muted-foreground">{item.year ?? "연도 미상"}</span>
        <span className="text-muted-foreground">수집 {item.ingested_at ? formatDate(item.ingested_at) : "미상"}</span>
        {item.basis !== "image_vision" && <Badge variant="outline">{item.basis_label}</Badge>}
        {item.needs_check && <Badge variant="warning">{item.needs_check_label ?? "세부 확인 필요"}</Badge>}
        {item.basis === "image_vision" && (
          <>
            <Badge variant="info">
              <ScanSearch className="mr-1 size-3" aria-hidden="true" />
              이미지 판독
            </Badge>
            <Link to={`/search?q=${encodeURIComponent(item.doc_id)}`} className="inline-flex items-center gap-0.5 underline">
              원본 보기 <ExternalLink className="size-3" aria-hidden="true" />
            </Link>
          </>
        )}
        {item.support && <Badge variant={SUPPORT_VARIANT[item.support] ?? "outline"}>Argon {item.support}</Badge>}
        {item.decision && <Badge variant="success">{DECISION_LABEL[item.decision] ?? item.decision}</Badge>}
        {!item.in_snapshot && <Badge variant="destructive">검색 집합 밖</Badge>}
      </div>
      <blockquote className="max-h-48 overflow-y-auto rounded bg-muted/60 p-2">
        <UntrustedText as="p" text={item.text || "(발췌 없음)"} />
      </blockquote>
      <fieldset disabled={disabled} className="space-y-2">
        <legend className="sr-only">{item.evidence_id} 판단</legend>
        <div role="radiogroup" aria-label={`${item.title ?? item.evidence_id} 판단`} className="flex flex-wrap gap-1">
          {ACTIONS.map((a) => {
            const on = action === a.id;
            return (
              <label
                key={a.id}
                className={cn(
                  "inline-flex min-h-9 cursor-pointer items-center gap-1.5 rounded-md border px-2.5 text-sm has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring",
                  on ? "border-primary bg-primary text-primary-foreground" : "hover:bg-accent",
                )}
              >
                <input type="radio" name={groupId} value={a.id} checked={on} onChange={() => onChange({ action: a.id, replacement: a.id === "replace" ? others[0]?.id : undefined })} className="sr-only" />
                {a.label}
              </label>
            );
          })}
          {action && (
            <Button type="button" variant="ghost" size="sm" onClick={() => onChange(null)}>
              선택 해제
            </Button>
          )}
        </div>
        {action === "replace" && (
          <div className="space-y-1">
            <Label htmlFor={`rep-${item.evidence_id}`}>바꿀 근거 (이번 run 의 검색 집합 안에서만)</Label>
            {others.length === 0 ? (
              <p className="text-xs text-destructive">바꿀 다른 근거가 없습니다.</p>
            ) : (
              <Select id={`rep-${item.evidence_id}`} value={pending?.replacement ?? ""} onChange={(e) => onChange({ action: "replace", replacement: e.target.value })}>
                {others.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.title ?? c.doc_id} ({c.id})
                  </option>
                ))}
              </Select>
            )}
          </div>
        )}
      </fieldset>
    </li>
  );
}

/** U1 근거 패널 — 문장 하나의 근거마다 발췌·메타·근거 수준·Argon 적합성·제안자 판단(승인/교체/제외 → 새 버전). */
export function EvidencePanel({ runId, sentenceId, sentenceText, citations, problems = [], baseVersion, strategyDraft, onClose }: EvidencePanelProps) {
  const q = useSentenceEvidence(runId, sentenceId);
  const decide = useDecideEvidence(runId);
  const qc = useQueryClient();
  const { toast } = useToast();
  const [pending, setPending] = React.useState<Pending>({});
  const [conflict, setConflict] = React.useState(false);
  React.useEffect(() => {
    setPending({});
    setConflict(false);
  }, [sentenceId]);

  const alerts = problems.filter((p) => EVIDENCE_ALERT_CODES.has(p.code));
  const count = Object.keys(pending).length;

  const save = async () => {
    if (!sentenceId) return;
    const decisions = Object.entries(pending).map(([evidence_id, p]) => ({
      sentence_id: sentenceId,
      evidence_id,
      action: p.action,
      replacement: p.action === "replace" ? p.replacement ?? null : null,
    }));
    try {
      const out = await decide.mutateAsync({ decisions, base_version: baseVersion, note: "근거 판단" });
      setPending({});
      toast(out.version === baseVersion ? "바뀐 판단이 없어 새 버전을 만들지 않았습니다." : `근거 판단을 v${out.version} 으로 저장했습니다.`, "success");
      onClose();
    } catch (e) {
      if (isApiError(e) && e.status === 409) setConflict(true);
    }
  };
  const reload = async () => {
    setConflict(false);
    setPending({});
    await qc.invalidateQueries({ queryKey: keys.run(runId) });
    onClose();
  };

  return (
    <Dialog open={sentenceId !== null} onClose={onClose} title="근거 보기" description={sentenceId ?? undefined} className="w-[min(96vw,48rem)]">
      {sentenceText && <UntrustedText as="p" text={sentenceText} className="mb-3 rounded border-l-4 border-primary bg-muted/40 p-2 text-sm" />}
      {strategyDraft && (
        <Badge variant="warning" className="mb-2">
          전략체계 초안(확인 전)
        </Badge>
      )}
      {alerts.map((p, i) => (
        <Alert key={i} variant="warning" className="mb-3">
          <div>
            <AlertTitle>{p.code === "evidence_mismatch" ? "Argon 판정: 근거가 문장을 뒷받침하지 않음" : "근거가 모두 제외됨"}</AlertTitle>
            <AlertDescription>
              <UntrustedText text={p.message} />
            </AlertDescription>
          </div>
        </Alert>
      ))}
      {conflict ? (
        <Alert variant="destructive" role="alert">
          <div className="flex-1">
            <AlertTitle>다른 곳에서 먼저 저장되었습니다</AlertTitle>
            <AlertDescription>기준 버전 v{baseVersion} 이 최신이 아닙니다. 최신 버전을 불러온 뒤 다시 판단하십시오.</AlertDescription>
            <Button size="sm" className="mt-2" onClick={reload}>
              최신 버전 불러오기
            </Button>
          </div>
        </Alert>
      ) : (
        <ProblemBanner error={decide.error} />
      )}
      {q.isPending ? (
        <SkeletonBlock lines={5} />
      ) : q.error ? (
        <ProblemBanner error={q.error} onRetry={() => q.refetch()} />
      ) : q.data && q.data.evidence.length === 0 ? (
        <EmptyState title="이 문장에는 근거가 없습니다" description="제안자 입력이나 앱 규칙으로 만든 문장입니다." className="min-h-28" />
      ) : q.data ? (
        <>
          <p className="mb-2 text-xs text-muted-foreground">발췌·제목은 수집 자료(비신뢰)입니다. 판단은 문장×근거 단위로 저장되어 새 버전이 됩니다.</p>
          <ul className="space-y-3">
            {q.data.evidence.map((it) => (
              <EvidenceCard
                key={it.evidence_id}
                item={it}
                pending={pending[it.evidence_id]}
                onChange={(p) =>
                  setPending((s) => {
                    const next = { ...s };
                    if (p) next[it.evidence_id] = p;
                    else delete next[it.evidence_id];
                    return next;
                  })
                }
                citations={citations}
                disabled={decide.isPending || conflict}
              />
            ))}
          </ul>
          <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
            <span className="text-sm text-muted-foreground">판단 {count}건 (v{baseVersion} 기준)</span>
            <Button onClick={save} disabled={count === 0 || decide.isPending || conflict}>
              {decide.isPending ? "저장 중…" : "판단 저장"}
            </Button>
          </div>
        </>
      ) : null}
    </Dialog>
  );
}
