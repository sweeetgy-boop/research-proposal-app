import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { saveSectionAnswers } from "@/api/endpoints";
import { usabilityKeys, useSectionQuestions } from "@/api/hooks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { useToast } from "@/components/ui/toast";
import { sectionTitle } from "@/lib/sections";

/** U3 보완 질문 — 섹션 체크리스트에서 빠진 요소를 묻고, 답은 제안자 입력으로 저장(다음 다시 쓰기 프롬프트에 들어간다). */
export function SectionQuestions({ runId, sectionKey, onClose }: { runId: string; sectionKey: string | null; onClose: () => void }) {
  const q = useSectionQuestions(runId, sectionKey);
  const qc = useQueryClient();
  const { toast } = useToast();
  const [answers, setAnswers] = React.useState<Record<string, string>>({});
  React.useEffect(() => setAnswers({}), [sectionKey]);
  const save = useMutation({
    mutationFn: () => saveSectionAnswers(runId, sectionKey ?? "", answers),
    onSuccess: () => {
      toast("답을 저장했습니다. 다음 AI 다시 쓰기에 반영됩니다.", "success");
      setAnswers({});
      qc.invalidateQueries({ queryKey: usabilityKeys.questions(runId, sectionKey ?? "") });
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
      description="체크리스트에서 본문에 빠진 요소를 묻습니다. 답은 초안을 바꾸지 않고 저장만 되며, AI 다시 쓰기 때 [제안자 보완 메모]로 들어갑니다."
      footer={
        data ? (
          <>
            <Button variant="outline" onClick={onClose}>
              닫기
            </Button>
            <Button onClick={() => save.mutate()} disabled={!filled || save.isPending}>
              {save.isPending ? "저장 중…" : "답 저장"}
            </Button>
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
          보완 질문을 쓸 수 없습니다 (꺼져 있거나 체크리스트가 없는 섹션).
        </p>
      ) : data ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            {coverage !== null ? <Badge variant={coverage >= 0.8 ? "success" : "warning"}>체크리스트 충족 {Math.round(coverage * 100)}%</Badge> : <Badge variant="outline">체크리스트 없음</Badge>}
            {Object.keys(data.answers).length > 0 && <Badge variant="info">저장된 답 {Object.keys(data.answers).length}개</Badge>}
          </div>
          <ProblemBanner error={save.error} />
          {data.questions.length === 0 ? (
            <p className="text-sm text-muted-foreground">빠진 요소가 없습니다.</p>
          ) : (
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                if (filled) save.mutate();
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
