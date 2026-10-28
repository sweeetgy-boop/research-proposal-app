import * as React from "react";
import { Lightbulb, PencilLine, RefreshCw } from "lucide-react";
import type { PlanRecommendation, PlanRecommendations } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { UntrustedText } from "@/components/UntrustedText";
import { AiCancelledNote, AiWaiting } from "@/components/AiWaiting";

export const REFS_SHOWN = 3;

const DIFF_VARIANT: Record<string, "success" | "secondary" | "warning"> = {
  high: "success",
  mid: "secondary",
  low: "warning",
};

export interface CardsWaiting {
  pending: boolean;
  elapsed: number;
  cancelled: boolean;
  onCancel: () => void;
}

/** 차별화 과제안 고르기 — 카드(가제·연구목표·연구방법·적용범위·차이·근거). 모델 출력(비신뢰).
 *  v3(ADR 0039): 근거는 제목 + 자료원(상위 3건, 나머지는 [더 보기]), 겹침 경고는 ② 판정과 같은 기준의 재판정 결과
 *  (가까운 과제 제목 1~2건 + 판정의 한 줄 겹치는 점), 카드는 차별성 높은 순. */
export function PlanCards({
  rec,
  waiting,
  chosenIndex,
  stale,
  onPick,
  onKeepOriginal,
  onWrite,
  onRegenerate,
}: {
  rec: PlanRecommendations | null | undefined;
  waiting: CardsWaiting;
  chosenIndex: number | null;
  /** 과제안을 만든 뒤 [유사함] 선택이 바뀌었다 */
  stale: boolean;
  onPick: (card: PlanRecommendation) => void;
  onKeepOriginal: () => void;
  onWrite: () => void;
  onRegenerate: () => void;
}) {
  const loading = waiting.pending;
  const header = (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 id="plan-cards-heading" className="flex items-center gap-2 text-lg font-semibold">
        <Lightbulb className="size-5" aria-hidden="true" />
        차별화 과제안 고르기
      </h2>
      <Button variant={stale ? "default" : "outline"} size="sm" onClick={onRegenerate} disabled={loading}>
        <RefreshCw className={loading ? "animate-spin" : ""} aria-hidden="true" />
        {loading ? "만드는 중…" : rec ? "과제안 다시 만들기" : "과제안 만들기"}
      </Button>
    </div>
  );
  const waitingRow = (
    <>
      <AiWaiting pending={waiting.pending} elapsed={waiting.elapsed} onCancel={waiting.onCancel} what="차별화 과제안 만들기" />
      <AiCancelledNote show={waiting.cancelled && !waiting.pending} />
    </>
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
  if (loading && !rec) {
    return (
      <section className="space-y-3" aria-busy="true" aria-labelledby="plan-cards-heading" id="plan-cards">
        {header}
        {waitingRow}
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
      rec?.no_recommendation_reason || rec?.skipped_label || "과제안이 없습니다 — [과제안 만들기] 로 받거나 직접 작성하십시오.";
    return (
      <section className="space-y-3" aria-labelledby="plan-cards-heading" id="plan-cards">
        {header}
        {waitingRow}
        {staleNote}
        <EmptyState
          icon={Lightbulb}
          title={rec ? "추천 0건" : "과제안 없음"}
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
    <section className="space-y-3" aria-labelledby="plan-cards-heading" id="plan-cards">
      {header}
      {waitingRow}
      {staleNote}
      <p className="text-sm text-muted-foreground">
        기존 과제와 겹치지 않는 방향 {cards.length}건입니다 — 차별성이 높은 안부터 놓았습니다(차별성은 판단, 모델 출력 — 확인 뒤 사용).
        {rec?.regenerated ? " 검증에서 걸러진 안이 있어 한 번 더 받았습니다." : ""}
        {rec?.overlap_regenerated ? ` 기존 과제와 겹친 ${rec.overlap_regenerated}건은 겹치는 부분을 피해 다시 만들었습니다.` : ""} 고른 안은 ③ 초안의
        입력과 비교표의 제안 과제 칸이 됩니다.
      </p>
      <ul className="grid gap-3 md:grid-cols-2">
        {cards.map((c) => (
          <li key={c.index} id={`rec-${c.index}`}>
            <PlanCard card={c} chosen={chosenIndex === c.index} onPick={() => onPick(c)} />
          </li>
        ))}
      </ul>
      {actions}
      <ExcludedList items={excluded} />
    </section>
  );
}

function PlanCard({ card: c, chosen, onPick }: { card: PlanRecommendation; chosen: boolean; onPick: () => void }) {
  const [open, setOpen] = React.useState(false);
  const refs = c.refs ?? [];
  const shown = open ? refs : refs.slice(0, REFS_SHOWN);
  const overlapTitles = c.overlap_titles ?? [];
  const warn = overlapTitles.length > 0 || c.overlap_warning.length > 0;
  return (
    <Card className={chosen ? "border-primary" : undefined} data-testid="plan-card">
      <CardHeader>
        <CardTitle className="flex items-start justify-between gap-2 text-base">
          <UntrustedText text={c.title} />
          <span className="flex shrink-0 flex-wrap justify-end gap-1">
            {c.added && <Badge variant="secondary">새로 만든 안</Badge>}
            {chosen && <Badge>선택됨</Badge>}
          </span>
        </CardTitle>
        {c.difference_label && (
          <p className="text-xs">
            <Badge variant={DIFF_VARIANT[c.difference ?? "mid"] ?? "secondary"}>차별성 {c.difference_label}</Badge>
            <span className="ml-1 text-muted-foreground">판단</span>
          </p>
        )}
      </CardHeader>
      <CardContent>
        <dl className="space-y-2 text-sm">
          <Field label="연구목표" text={c.goal || c.summary} />
          <Field label="연구방법" text={c.method || "정보 없음"} />
          <Field label="적용범위" text={c.scope || "정보 없음"} />
          <Field label="기존 과제 대비 차이" text={c.differentiation} />
          <div>
            <dt className="font-medium">근거 과제·자료</dt>
            <dd className="text-xs text-muted-foreground">
              {refs.length === 0 ? (
                "없음"
              ) : (
                <>
                  <ul className="list-disc space-y-0.5 pl-4" data-testid="card-refs">
                    {shown.map((r) => (
                      <li key={r.doc_id}>
                        <UntrustedText text={r.title} />
                        {r.source_label ? ` · ${r.source_label}` : ""}
                      </li>
                    ))}
                  </ul>
                  {refs.length > REFS_SHOWN && (
                    <Button variant="link" size="sm" className="h-auto px-0 text-xs" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
                      {open ? "접기" : `더 보기 (${refs.length - REFS_SHOWN}건)`}
                    </Button>
                  )}
                </>
              )}
            </dd>
          </div>
        </dl>
        {c.regenerated && (
          <p className="mt-2 text-xs text-muted-foreground">기존 과제와 겹쳐 겹치는 부분을 피해 한 번 다시 만든 안입니다.</p>
        )}
        {warn && (
          <div role="status" className="mt-2 rounded-md border border-warning/60 p-2 text-sm" data-testid="overlap-warning">
            {overlapTitles.length > 0 ? (
              <>
                <p>
                  이 안도 기존 과제와 가깝습니다:{" "}
                  {overlapTitles.map((t, i) => (
                    <React.Fragment key={i}>
                      {i > 0 ? ", " : ""}「<UntrustedText text={t} />」
                    </React.Fragment>
                  ))}
                </p>
                {c.overlap_reason && (
                  <p className="mt-1 text-xs">
                    겹치는 점: <UntrustedText text={c.overlap_reason} />
                  </p>
                )}
                {c.overlap_by_label && <p className="mt-1 text-xs text-muted-foreground">{c.overlap_by_label}</p>}
              </>
            ) : (
              <p>이 안도 기존 과제 {c.overlap_warning.length}건과 가깝습니다.</p>
            )}
          </div>
        )}
      </CardContent>
      <CardFooter>
        <Button size="sm" onClick={onPick} aria-pressed={chosen}>
          {chosen ? "이 안으로 진행 중" : "이 안으로 진행"}
        </Button>
      </CardFooter>
    </Card>
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
