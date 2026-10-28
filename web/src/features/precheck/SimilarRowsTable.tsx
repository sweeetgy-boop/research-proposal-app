import { ShieldCheck } from "lucide-react";
import type { PrecheckAlert, SimilarChoiceValue } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/EmptyState";
import { UntrustedText } from "@/components/UntrustedText";
import { LiveBadge } from "@/features/live/LiveBadge";
import { tierLabel } from "@/lib/tiers";
import { cn } from "@/lib/utils";
import { choiceOf, levelOf, type ChoiceMap } from "./model";

const VERDICT_VARIANT: Record<string, "destructive" | "warning" | "secondary"> = {
  same: "destructive",
  partial: "warning",
  different: "secondary",
};
const LEVEL_VARIANT: Record<string, "destructive" | "warning" | "secondary"> = {
  blocking: "destructive",
  near: "warning",
  low: "secondary",
};

/** ② 유사과제 행 — 판정 칸은 AI 판정(같다→차단·일부 겹침→근접·다르다→관련 낮음), AI 판정 전엔 규칙 기준.
 *  관련도는 reranker 점수의 쉬운 말 하나(높음·보통·낮음) — 유사도 숫자·내부 번호는 보이지 않는다 (ADR 0039).
 *  행마다 [유사함]/[관련 없음]. 제목·이유는 비신뢰 텍스트. */
export function SimilarRowsTable({
  alerts,
  choices,
  onChoose,
  judging = false,
}: {
  alerts: PrecheckAlert[];
  choices: ChoiceMap;
  onChoose: (docId: string, choice: SimilarChoiceValue | null) => void;
  /** AI 판정을 기다리는 중 */
  judging?: boolean;
}) {
  if (alerts.length === 0) {
    return <EmptyState icon={ShieldCheck} title="유사과제가 없습니다" description="관련도·핵심 키워드 기준을 넘는 기존 과제가 없습니다." />;
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
            const lv = levelOf(a);
            const struck = lv.level === "blocking" && choice === "unrelated";
            const meta = [a.source_label, merged > 0 ? `같은 제목 ${merged + 1}건 묶음` : "", a.status_label ?? ""].filter(Boolean);
            return (
              <tr key={a.doc_id} className={cn("border-t align-top", choice === "similar" && "bg-primary/5")} data-testid="similar-row">
                <td className="whitespace-nowrap px-3 py-2">{tierLabel(a)}</td>
                <td className="px-3 py-2">
                  <UntrustedText text={a.title} className="font-medium" />
                  {a.live && <LiveBadge className="ml-2 align-middle" />}
                  {meta.length > 0 && <p className="text-xs text-muted-foreground">{meta.join(" · ")}</p>}
                  {a.keywords.length > 0 && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      겹친 핵심 키워드: <UntrustedText text={a.keywords.join(", ")} />
                    </p>
                  )}
                </td>
                <td className="whitespace-nowrap px-3 py-2" data-testid="relevance">
                  {a.relevance_label ?? "—"}
                </td>
                <td className="px-3 py-2">
                  {a.judgment ? (
                    <>
                      <Badge variant={VERDICT_VARIANT[a.judgment] ?? "secondary"}>{a.judgment_label ?? a.judgment}</Badge>
                      <UntrustedText as="p" text={a.judgment_reason} className="mt-1 text-xs" />
                    </>
                  ) : (
                    <span className="text-xs text-muted-foreground">{judging ? "AI 판정 기다리는 중" : a.judgment_reason || "규칙 기준"}</span>
                  )}
                </td>
                <td className="px-3 py-2" data-testid="level">
                  <Badge variant={LEVEL_VARIANT[lv.level]} className={cn(struck && "line-through opacity-60")}>
                    {lv.label}
                    {struck ? " 해제" : ""}
                  </Badge>
                  {lv.basis === "rule" && <span className="mt-1 block text-xs text-muted-foreground">규칙 기준</span>}
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
