import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Wand2 } from "lucide-react";
import { saveSectionAnswers } from "@/api/endpoints";
import { sectionQuestionsV2 } from "@/api/editai";
import { isApiError } from "@/api/client";
import { usabilityKeys } from "@/api/hooks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { useToast } from "@/components/ui/toast";
import { sectionTitle } from "@/lib/sections";

/** U3 보완 질문 — Argon 이 섹션 본문·근거·양식 작성 지침을 읽고 빠지거나 약한 부분을 묻는다(실패하면 로컬 → 체크리스트).
 *  답은 제안자 입력으로 저장되어 다음 AI 다시 쓰기의 [제안자 보완 메모] 로 들어간다. [답 반영해 다시 쓰기] 는 저장 뒤 바로 다시 쓰기로. */
export function SectionQuestions({
  runId,
  sectionKey,
  onClose,
  onRewrite,
}: {
  runId: string;
  sectionKey: string | null;
  onClose: () => void;
  /** 답 저장 뒤 그 섹션 AI 다시 쓰기를 연다 */
  onRewrite?: (key: string) => void;
}) {
  const [refresh, setRefresh] = React.useState(0);
  const q = useQuery({
    queryKey: [...usabilityKeys.questions(runId, sectionKey ?? ""), refresh],
    queryFn: async () => {
      try {
        return await sectionQuestionsV2(runId, sectionKey ?? "", refresh > 0);
      } catch (e) {
        if (isApiError(e) && e.status === 503) return null;
        throw e;
      }
    },
    enabled: sectionKey !== null,
  });
  const qc = useQueryClient();
  const { toast } = useToast();
  const [answers, setAnswers] = React.useState<Record<string, string>>({});
  React.useEffect(() => setAnswers({}), [sectionKey]);
  const save = useMutation({
    mutationFn: async (rewriteAfter: boolean) => {
      const filledNow = Object.values(answers).some((v) => v.trim());
      if (filledNow) await saveSectionAnswers(runId, sectionKey ?? "", answers);
      return { rewriteAfter, saved: filledNow };
    },
    onSuccess: ({ rewriteAfter, saved }) => {
      if (saved) toast(rewriteAfter ? "답을 저장했습니다. 답을 반영해 다시 씁니다." : "답을 저장했습니다. 다음 AI 다시 쓰기에 반영됩니다.", "success");
      setAnswers({});
      qc.invalidateQueries({ queryKey: usabilityKeys.questions(runId, sectionKey ?? "") });
      qc.invalidateQueries({ queryKey: ["run", runId, "changes"] });
      if (rewriteAfter && sectionKey && onRewrite) onRewrite(sectionKey);
    },
  });
  const data = q.data;
  const filled = Object.values(answers).some((v) => v.trim());
  const coverage = data?.coverage ?? null;

  return (
    <Dialog
      open={sectionKey !== null}
      onClose={onClose}
      title={`보완 질문 — ${sectionKey ? sectionTitle(sectionKey) : ""}`}
      description="Argon 이 본문·근거·양식 작성 지침을 읽고 빠지거나 약한 부분을 묻습니다. 답은 초안을 바꾸지 않고 저장되며, AI 다시 쓰기 때 [제안자 보완 메모]로 들어갑니다."
      footer={
        data ? (
          <>
            <Button variant="outline" onClick={onClose}>
              닫기
            </Button>
            <Button variant="secondary" onClick={() => save.mutate(false)} disabled={!filled || save.isPending}>
              {save.isPending ? "저장 중…" : "답 저장"}
            </Button>
            {onRewrite && (
              <Button onClick={() => save.mutate(true)} disabled={save.isPending || (!filled && Object.keys(data.answers).length === 0)}>
                <Wand2 aria-hidden="true" />
                답 반영해 다시 쓰기
              </Button>
            )}
          </>
        ) : undefined
      }
    >
      {q.isPending ? (
        <SkeletonBlock lines={4} />
      ) : q.error ? (
        <ProblemBanner error={q.error} onRetry={() => q.refetch()} />
      ) : data === null ? (
        <p className="text-sm text-muted-foreground" role="status">
          보완 질문을 쓸 수 없습니다 (기능이 꺼져 있습니다).
        </p>
      ) : data ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            {data.source_label && <Badge variant="info">{data.source_label}</Badge>}
            {coverage !== null && <Badge variant={coverage >= 0.8 ? "success" : "warning"}>체크리스트 충족 {Math.round(coverage * 100)}%</Badge>}
            {Object.keys(data.answers).length > 0 && <Badge variant="info">저장된 답 {Object.keys(data.answers).length}개</Badge>}
          </div>
          <ProblemBanner error={save.error} />
          {data.reason_label && (
            <div className="flex flex-wrap items-center gap-2 rounded border border-warning/60 p-2 text-sm" role="status">
              <span>모델이 답하지 못해 {data.source === "checklist" || data.source === "strengthen" ? "체크리스트로 물었습니다" : "질문이 없습니다"} — 사유: {data.reason_label}</span>
              <Button size="sm" variant="outline" onClick={() => setRefresh((n) => n + 1)} disabled={q.isFetching}>
                다시 시도
              </Button>
            </div>
          )}
          {data.questions.length === 0 ? (
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span>빠진 요소를 찾지 못했습니다 (해당 없음).</span>
              <Button size="sm" variant="ghost" onClick={() => setRefresh((n) => n + 1)} disabled={q.isFetching}>
                다시 묻기
              </Button>
            </div>
          ) : (
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                if (filled) save.mutate(false);
              }}
            >
              {data.questions.map((x) => (
                <div key={x.element} className="space-y-1">
                  <Label htmlFor={`sq-${x.element}`}>
                    <span className="text-xs text-muted-foreground">[{x.element}] </span>
                    {x.question}
                  </Label>
                  <Textarea id={`sq-${x.element}`} rows={2} maxLength={2000} value={answers[x.element] ?? data.answers[x.element] ?? ""} onChange={(e) => setAnswers((s) => ({ ...s, [x.element]: e.target.value }))} />
                </div>
              ))}
            </form>
          )}
          {Object.keys(data.answers).length > 0 && (
            <details className="text-sm">
              <summary className="cursor-pointer font-medium">저장된 답 보기</summary>
              <dl className="mt-2 space-y-1">
                {Object.entries(data.answers).map(([k, v]) => (
                  <div key={k} className="rounded border p-2">
                    <dt className="text-xs text-muted-foreground">{k}</dt>
                    <dd>{v}</dd>
                  </div>
                ))}
              </dl>
            </details>
          )}
        </div>
      ) : null}
    </Dialog>
  );
}
