import { Lightbulb, PencilLine, RefreshCw } from "lucide-react";
import type { PlanRecommendation, PlanRecommendations } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { UntrustedText } from "@/components/UntrustedText";

/** 차별화 과제안 고르기 — 2~5개 카드(가제·연구목표·연구방법·적용범위·차이 한 줄·근거). 모델 출력(비신뢰). */
export function PlanCards({
  rec,
  loading,
  chosenIndex,
  stale,
  onPick,
  onKeepOriginal,
  onWrite,
  onRegenerate,
}: {
  rec: PlanRecommendations | null | undefined;
  loading: boolean;
  chosenIndex: number | null;
  /** 과제안을 만든 뒤 [유사함] 선택이 바뀌었다 */
  stale: boolean;
  onPick: (card: PlanRecommendation) => void;
  onKeepOriginal: () => void;
  onWrite: () => void;
  onRegenerate: () => void;
}) {
  const header = (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="flex items-center gap-2 text-lg font-semibold">
        <Lightbulb className="size-5" aria-hidden="true" />
        차별화 과제안 고르기
      </h2>
      <Button variant={stale ? "default" : "outline"} size="sm" onClick={onRegenerate} disabled={loading}>
        <RefreshCw className={loading ? "animate-spin" : ""} aria-hidden="true" />
        {loading ? "만드는 중…" : "과제안 다시 만들기"}
      </Button>
    </div>
  );
  const actions = (
    <div className="flex flex-wrap gap-2">
      <Button variant="secondary" onClick={onKeepOriginal}>
        원래 아이디어 유지
      </Button>
      <Button variant="outline" onClick={onWrite}>
        <PencilLine aria-hidden="true" />
        직접 작성
      </Button>
    </div>
  );
  if (loading) {
    return (
      <section className="space-y-3" aria-busy="true">
        {header}
        <SkeletonBlock lines={4} />
      </section>
    );
  }
  const cards = rec?.recommendations ?? [];
  const excluded = rec?.discarded ?? [];
  const staleNote = stale ? (
    <p role="status" className="rounded-md border border-warning/60 p-2 text-sm">
      유사함으로 고른 과제가 바뀌었습니다. [과제안 다시 만들기] 로 고른 과제와 겹치지 않는 안을 다시 받으십시오.
    </p>
  ) : null;
  if (cards.length === 0) {
    const reason =
      rec?.no_recommendation_reason || rec?.skipped_label || "과제안이 없습니다 — [과제안 다시 만들기] 로 다시 받거나 직접 작성하십시오.";
    return (
      <section className="space-y-3">
        {header}
        {staleNote}
        <EmptyState
          icon={Lightbulb}
          title="추천 0건"
          description={reason}
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Button onClick={onKeepOriginal} variant="secondary">
                원래 아이디어로 진행
              </Button>
              <Button variant="outline" onClick={onWrite}>
                직접 작성
              </Button>
            </div>
          }
        />
        <ExcludedList items={excluded} />
      </section>
    );
  }
  return (
    <section className="space-y-3">
      {header}
      {staleNote}
      <p className="text-sm text-muted-foreground">
        [유사함] 으로 고른 과제와 겹치지 않는 방향 {cards.length}건입니다 (모델 출력 — 확인 뒤 사용).
        {rec?.regenerated ? " 검증에서 걸러진 안이 있어 한 번 더 받았습니다." : ""} 고른 안은 ③ 초안의 입력과 비교표의 제안 과제 칸이 됩니다.
      </p>
      <ul className="grid gap-3 md:grid-cols-2">
        {cards.map((c) => {
          const chosen = chosenIndex === c.index;
          const refs = Array.from(new Set([...(c.compared_with ?? []), ...(c.evidence ?? [])]));
          return (
            <li key={c.index} id={`rec-${c.index}`}>
              <Card className={chosen ? "border-primary" : undefined}>
                <CardHeader>
                  <CardTitle className="flex items-start justify-between gap-2 text-base">
                    <UntrustedText text={c.title} />
                    {chosen && <Badge>선택됨</Badge>}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <dl className="space-y-2 text-sm">
                    <Field label="연구목표" text={c.goal || c.summary} />
                    <Field label="연구방법" text={c.method || "정보 없음"} />
                    <Field label="적용범위" text={c.scope || "정보 없음"} />
                    <Field label="기존 과제 대비 차이" text={c.differentiation} />
                    <div>
                      <dt className="font-medium">근거 과제·자료</dt>
                      <dd className="text-xs text-muted-foreground">{refs.length ? refs.join(", ") : "없음"}</dd>
                    </div>
                  </dl>
                  {c.overlap_warning.length > 0 && (
                    <p role="status" className="mt-2 rounded-md border border-warning/60 p-2 text-sm">
                      이 안도 기존 과제 {c.overlap_warning.length}건과 가깝습니다 ({c.overlap_warning.join(", ")}).
                    </p>
                  )}
                </CardContent>
                <CardFooter>
                  <Button size="sm" onClick={() => onPick(c)} aria-pressed={chosen}>
                    {chosen ? "이 안으로 진행 중" : "이 안으로 진행"}
                  </Button>
                </CardFooter>
              </Card>
            </li>
          );
        })}
      </ul>
      {actions}
      <ExcludedList items={excluded} />
    </section>
  );
}

function Field({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <dt className="font-medium">{label}</dt>
      <dd>
        <UntrustedText text={text} />
      </dd>
    </div>
  );
}

function ExcludedList({ items }: { items: { title?: string; reason_label?: string; reason?: string }[] }) {
  if (items.length === 0) return null;
  return (
    <details className="rounded-md border p-3 text-sm">
      <summary className="cursor-pointer">검증에서 제외된 안 {items.length}건 — 이유 보기</summary>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-muted-foreground">
        {items.map((d, i) => (
          <li key={i}>
            <UntrustedText text={d.title || "(제목 없음)"} /> — {d.reason_label ?? "검증 규칙에 맞지 않음"}
          </li>
        ))}
      </ul>
    </details>
  );
}
