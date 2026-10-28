import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Wand2 } from "lucide-react";
import { rewriteSectionV2 } from "@/api/editai";
import { keys, useApplyRewrite } from "@/api/hooks";
import { isApiError } from "@/api/client";
import { defaultChosen } from "./model";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { OriginBadge } from "@/components/OriginBadge";
import { UntrustedText } from "@/components/UntrustedText";
import { sectionTitle } from "@/lib/sections";
import { cn } from "@/lib/utils";

export interface SectionRewriteProps {
  runId: string;
  sectionKey: string | null;
  baseVersion: number;
  /** 저장하지 않은 편집이 있으면 반영을 막는다 (버전이 바뀌면 편집 기준이 어긋난다) */
  dirty?: boolean;
  onClose: () => void;
  onApplied: (version: number) => void;
  /** 2-가-(1) 에 정책 근거가 없을 때 — 정책적 중요도 작성안으로 (부모가 연다) */
  onPolicy?: () => void;
}

/** U3 섹션 AI 다시 쓰기 — 현재 문장과 후보를 나란히, 고른 후보만 반영 → 새 버전(origin edit, "AI 다시 쓰기"). */
export function SectionRewrite({ runId, sectionKey, baseVersion, dirty, onClose, onApplied, onPolicy }: SectionRewriteProps) {
  const qc = useQueryClient();
  const [chosen, setChosen] = React.useState<number[]>([]);
  const [conflict, setConflict] = React.useState(false);
  const rewrite = useMutation({
    mutationFn: (key: string) => rewriteSectionV2(runId, key),
    onSuccess: (out) => setChosen(defaultChosen(out)),
  });
  const apply = useApplyRewrite(runId, sectionKey ?? "");

  React.useEffect(() => {
    setConflict(false);
    if (sectionKey) rewrite.mutate(sectionKey);
    else rewrite.reset();
  }, [sectionKey]);

  const out = rewrite.data;
  const newCount = out ? (out.new_count ?? out.candidate.filter((c) => !["proposer_edit", "proposer_input", "proposer", "app"].includes(c.origin)).length) : 0;
  const isNew = out?.mode === "new";
  const unavailable = isApiError(rewrite.error) && rewrite.error.status === 503;
  const rejected = isApiError(rewrite.error) && rewrite.error.status === 409;
  const toggle = (i: number, on: boolean) => setChosen((s) => (on ? [...new Set([...s, i])].sort((a, b) => a - b) : s.filter((x) => x !== i)));

  const doApply = async () => {
    if (!sectionKey) return;
    try {
      const v = await apply.mutateAsync({ chosen, base_version: baseVersion, note: "" });
      onApplied(v.version);
    } catch (e) {
      if (isApiError(e) && e.status === 409) setConflict(true);
    }
  };
  const reload = async () => {
    setConflict(false);
    await qc.invalidateQueries({ queryKey: keys.run(runId) });
    onClose();
  };

  return (
    <Dialog
      open={sectionKey !== null}
      onClose={onClose}
      title={`${isNew ? "AI 새로 쓰기" : "AI 다시 쓰기"} — ${sectionKey ? sectionTitle(sectionKey) : ""}`}
      description={
        isNew
          ? "빈 섹션입니다. Argon 이 이 섹션의 근거와 작성 규칙으로 새로 씁니다(실패하면 로컬 모델). 선택값은 바뀌지 않습니다."
          : "Argon 이 같은 지시·근거로 다시 씁니다(실패하면 로컬 모델). 제안자가 고친 문장은 보존되고 선택값은 바뀌지 않습니다."
      }
      className="w-[min(96vw,56rem)]"
      footer={
        out && !unavailable && newCount > 0 ? (
          <>
            <Button variant="outline" onClick={onClose}>
              닫기
            </Button>
            <Button onClick={doApply} disabled={apply.isPending || conflict || !!dirty || chosen.length === 0}>
              <Wand2 aria-hidden="true" />
              {apply.isPending ? "반영 중…" : `고른 ${chosen.length}문장 반영`}
            </Button>
          </>
        ) : undefined
      }
    >
      {dirty && (
        <Alert variant="warning" className="mb-3">
          <div>
            <AlertTitle>저장하지 않은 편집이 있습니다</AlertTitle>
            <AlertDescription>먼저 저장하거나 버린 뒤 반영할 수 있습니다 (후보는 볼 수 있습니다).</AlertDescription>
          </div>
        </Alert>
      )}
      {conflict && (
        <Alert variant="destructive" role="alert" className="mb-3">
          <div className="flex-1">
            <AlertTitle>기준 버전이 바뀌었습니다</AlertTitle>
            <AlertDescription>v{baseVersion} 이 최신이 아닙니다. 최신 버전을 불러온 뒤 다시 시도하십시오.</AlertDescription>
            <Button size="sm" className="mt-2" onClick={reload}>
              최신 버전 불러오기
            </Button>
          </div>
        </Alert>
      )}
      {rewrite.isPending ? (
        <div aria-busy="true" className="space-y-2">
          <p className="text-sm text-muted-foreground" aria-live="polite">후보를 쓰는 중입니다… (Argon, 실패하면 로컬 모델)</p>
          <SkeletonBlock lines={5} />
        </div>
      ) : unavailable ? (
        <Alert variant="info" role="status">
          <div>
            <AlertTitle>AI 다시 쓰기를 쓸 수 없습니다</AlertTitle>
            <AlertDescription>기능이 꺼져 있거나 쓸 수 있는 모델이 없습니다. 직접 수정으로 고치십시오.</AlertDescription>
          </div>
        </Alert>
      ) : rejected ? (
        <Alert variant="warning" role="status">
          <div>
            <AlertTitle>지금은 다시 쓸 수 없습니다</AlertTitle>
            <AlertDescription>{isApiError(rewrite.error) ? rewrite.error.problem.detail : ""}</AlertDescription>
          </div>
        </Alert>
      ) : rewrite.error ? (
        <ProblemBanner error={rewrite.error} onRetry={() => sectionKey && rewrite.mutate(sectionKey)} />
      ) : out && newCount === 0 ? (
        <Alert variant="warning" role="status">
          <div className="flex-1">
            <AlertTitle>후보 문장이 없습니다</AlertTitle>
            <AlertDescription>사유: {out.reason_label ?? "해당 없음"}</AlertDescription>
            <div className="mt-2 flex flex-wrap gap-2">
              {out.reason === "policy_basis_needed" && onPolicy && (
                <Button size="sm" onClick={onPolicy}>
                  정책적 중요도 작성안 보기
                </Button>
              )}
              {out.reason !== "app_section" && out.reason !== "policy_basis_needed" && (
                <Button size="sm" variant="outline" onClick={() => sectionKey && rewrite.mutate(sectionKey)}>
                  다시 시도
                </Button>
              )}
              <Button size="sm" variant="ghost" onClick={onClose}>
                닫기
              </Button>
            </div>
          </div>
        </Alert>
      ) : out ? (
        <div className="space-y-3">
          <ProblemBanner error={apply.error && !(isApiError(apply.error) && apply.error.status === 409) ? apply.error : null} />
          <p className="text-xs text-muted-foreground">
            {out.writer && <Badge variant="outline" className="mr-1">{out.writer.label}</Badge>}
            새 후보 {newCount}문장{out.dropped > 0 ? ` · 검증에서 버린 문장 ${out.dropped}` : ""}. 후보는 모델 출력(비신뢰)입니다 — 고른 행만 반영되고 보존 문장은 그대로 남습니다.
          </p>
          <div className="relative overflow-x-auto">
            <table className="w-full min-w-[36rem] text-sm">
              <caption className="sr-only">현재 문장과 다시 쓴 후보</caption>
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th scope="col" className="w-8 p-2">반영</th>
                  <th scope="col" className="w-1/2 p-2">현재</th>
                  <th scope="col" className="w-1/2 p-2">후보</th>
                </tr>
              </thead>
              <tbody>
                {out.rows.map((r) => {
                  const preserved = !!r.candidate?.preserved;
                  const selectable = !!r.candidate && !preserved;
                  const on = preserved || chosen.includes(r.index);
                  return (
                    <tr key={r.index} className={cn("border-t align-top", !on && r.candidate && "opacity-70")}>
                      <td className="p-2">
                        {r.candidate && (
                          <Label className="flex items-center">
                            <Checkbox checked={on} disabled={!selectable} onChange={(e) => toggle(r.index, e.target.checked)} />
                            <span className="sr-only">후보 {r.index + 1} 반영</span>
                          </Label>
                        )}
                      </td>
                      <td className="p-2">
                        {r.current ? (
                          <>
                            <UntrustedText as="p" text={r.current.text} />
                            <OriginBadge origin={r.current.origin} className="mt-1" />
                          </>
                        ) : (
                          <span className="text-muted-foreground">(없음)</span>
                        )}
                      </td>
                      <td className="p-2">
                        {r.candidate ? (
                          <>
                            <UntrustedText as="p" text={r.candidate.text} className={cn(r.current && r.current.text !== r.candidate.text && "diff-ins")} />
                            <div className="mt-1 flex flex-wrap gap-1">
                              <OriginBadge origin={r.candidate.origin} />
                              {preserved && <Badge variant="outline">보존</Badge>}
                              {r.candidate.evidence.length > 0 && <Badge variant="outline">근거 {r.candidate.evidence.length}</Badge>}
                            </div>
                          </>
                        ) : (
                          <span className="text-muted-foreground">(후보 없음 — 반영하면 빠집니다)</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </Dialog>
  );
}
