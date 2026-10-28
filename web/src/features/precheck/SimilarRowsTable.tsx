import { ShieldCheck } from "lucide-react";
import type { PrecheckAlert, SimilarChoiceValue } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/EmptyState";
import { UntrustedText } from "@/components/UntrustedText";
import { LiveBadge } from "@/features/live/LiveBadge";
import { tierLabel } from "@/lib/tiers";
import { cn } from "@/lib/utils";
import { choiceOf, type ChoiceMap } from "./model";

const VERDICT_VARIANT: Record<string, "destructive" | "warning" | "secondary"> = {
  same: "destructive",
  partial: "warning",
  different: "secondary",
};

/** ② 유사과제 행 — AI 판정(같다·일부 겹침·다르다)과 한 줄 이유, 행마다 [유사함]/[관련 없음]. 제목·이유는 비신뢰 텍스트. */
export function SimilarRowsTable({
  alerts,
  choices,
  onChoose,
}: {
  alerts: PrecheckAlert[];
  choices: ChoiceMap;
  onChoose: (docId: string, choice: SimilarChoiceValue | null) => void;
}) {
  if (alerts.length === 0) {
    return <EmptyState icon={ShieldCheck} title="유사과제가 없습니다" description="점수·핵심 키워드 기준을 넘는 기존 과제가 없습니다." />;
  }
  return (
    <div className="relative overflow-x-auto rounded-lg border">
      <table className="w-full min-w-[52rem] text-sm">
        <caption className="sr-only">유사과제 목록 — 행마다 유사함·관련 없음 선택</caption>
        <thead className="bg-muted/60 text-left text-muted-foreground">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">구분</th>
            <th scope="col" className="min-w-[14rem] px-3 py-2 font-medium">과제·문서</th>
            <th scope="col" className="px-3 py-2 font-medium">관련도</th>
            <th scope="col" className="min-w-[14rem] px-3 py-2 font-medium">AI 판정</th>
            <th scope="col" className="px-3 py-2 font-medium">판정</th>
            <th scope="col" className="min-w-[11rem] px-3 py-2 font-medium">선택</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((a) => {
            const choice = choiceOf(a, choices);
            const merged = a.merged_ids?.length ?? 0;
            const struck = a.blocking && choice === "unrelated";
            return (
              <tr key={a.doc_id} className={cn("border-t align-top", choice === "similar" && "bg-primary/5")}>
                <td className="whitespace-nowrap px-3 py-2">{tierLabel(a)}</td>
                <td className="px-3 py-2">
                  <UntrustedText text={a.title} className="font-medium" />
                  {a.live && <LiveBadge className="ml-2 align-middle" />}
                  <p className="text-xs text-muted-foreground">
                    {a.doc_id}
                    {merged > 0 ? ` · 같은 제목 ${merged + 1}건 묶음` : ""}
                    {a.status_label ? ` · ${a.status_label}` : ""}
                  </p>
                  {a.keywords.length > 0 && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      핵심 키워드: <UntrustedText text={a.keywords.join(", ")} />
                    </p>
                  )}
                </td>
                <td className="whitespace-nowrap px-3 py-2 tabular-nums">
                  {a.rerank_score !== null && a.rerank_score !== undefined ? a.rerank_score.toFixed(2) : "—"}
                  <span className="block text-xs text-muted-foreground">유사도 {a.similarity.toFixed(2)}</span>
                </td>
                <td className="px-3 py-2">
                  {a.judgment ? (
                    <>
                      <Badge variant={VERDICT_VARIANT[a.judgment] ?? "secondary"}>{a.judgment_label ?? a.judgment}</Badge>
                      <UntrustedText as="p" text={a.judgment_reason} className="mt-1 text-xs" />
                    </>
                  ) : (
                    <span className="text-xs text-muted-foreground">{a.judgment_reason || "규칙 기준"}</span>
                  )}
                </td>
                <td className="px-3 py-2">
                  {a.blocking ? (
                    <Badge variant="destructive" className={cn(struck && "line-through opacity-60")}>
                      차단{struck ? " 해제" : ""}
                    </Badge>
                  ) : (
                    <Badge variant="warning">근접</Badge>
                  )}
                </td>
                <td className="px-3 py-2">
                  <div role="group" aria-label={`${a.title} 선택`} className="flex flex-wrap gap-1">
                    {(
                      [
                        ["similar", "유사함"],
                        ["unrelated", "관련 없음"],
                      ] as const
                    ).map(([value, label]) => (
                      <Button
                        key={value}
                        size="sm"
                        variant={choice === value ? "default" : "outline"}
                        aria-pressed={choice === value}
                        onClick={() => onChoose(a.doc_id, choice === value ? null : value)}
                      >
                        {label}
                      </Button>
                    ))}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
