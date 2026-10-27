import * as React from "react";
import { Lightbulb, RefreshCw } from "lucide-react";
import type { RecommendationPreview, Recommendations } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { UntrustedText } from "@/components/UntrustedText";
import { EmptyState } from "@/components/EmptyState";
import { ProblemBanner } from "@/components/ProblemBanner";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { applyRecommendation } from "@/api/endpoints";
import { FIELD_LABELS } from "@/lib/validation";

const SKIP_REASON: Record<string, string> = {
  parse_failed: "모델 응답을 해석하지 못해 추천이 없습니다.",
  no_llm: "추천 모델이 없어 건너뛰었습니다.",
  no_candidates: "비교할 기존 과제가 없어 건너뛰었습니다.",
};

export function RecommendationCards({
  rec,
  chosenIndex,
  onChoose,
  onProceedOriginal,
  onRetry,
  retrying,
}: {
  rec: Recommendations | null | undefined;
  chosenIndex: number | null;
  onChoose: (index: number, preview: RecommendationPreview) => void;
  onProceedOriginal: () => void;
  onRetry: () => void;
  retrying: boolean;
}) {
  const [preview, setPreview] = React.useState<RecommendationPreview | null>(null);
  const [previewError, setPreviewError] = React.useState<unknown>(null);
  const [loading, setLoading] = React.useState<number | null>(null);

  const openPreview = async (index: number) => {
    if (!rec) return;
    setLoading(index);
    setPreviewError(null);
    try {
      setPreview(await applyRecommendation(rec.id, index));
    } catch (e) {
      setPreviewError(e);
    } finally {
      setLoading(null);
    }
  };

  const header = (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="flex items-center gap-2 text-lg font-semibold">
        <Lightbulb className="size-5" aria-hidden="true" />
        차별화 과제 추천
      </h2>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={onRetry} disabled={retrying}>
          <RefreshCw className={retrying ? "animate-spin" : ""} aria-hidden="true" />
          {retrying ? "받는 중…" : "다시 받기"}
        </Button>
      </div>
    </div>
  );

  if (retrying) {
    return (
      <section className="space-y-3" aria-busy="true">
        {header}
        <SkeletonBlock lines={4} />
      </section>
    );
  }

  if (!rec || rec.recommendations.length === 0) {
    const reason = rec?.no_recommendation_reason || (rec?.skipped_reason ? SKIP_REASON[rec.skipped_reason] ?? `건너뜀 (${rec.skipped_reason})` : "추천 결과가 없습니다.");
    return (
      <section className="space-y-3">
        {header}
        <EmptyState
          icon={Lightbulb}
          title="추천 0건"
          description={reason}
          action={
            <Button onClick={onProceedOriginal} variant="secondary">
              원래 아이디어로 진행
            </Button>
          }
        />
      </section>
    );
  }

  return (
    <section className="space-y-3">
      {header}
      <p className="text-sm text-muted-foreground">
        기존 과제와 겹치지 않는 방향 {rec.recommendations.length}건 (모델 출력 — 확인 뒤 사용). 고르면 가제·목표·차별화 방향이 입력에 채워지고, 고치고 나서 생성합니다.
      </p>
      <ProblemBanner error={previewError} />
      <ul className="grid gap-3 md:grid-cols-2">
        {rec.recommendations.map((r) => {
          const chosen = chosenIndex === r.index;
          return (
            <li key={r.index} id={`rec-${r.index}`}>
              <Card className={chosen ? "border-primary" : undefined}>
                <CardHeader>
                  <CardTitle className="flex items-start justify-between gap-2 text-base">
                    <UntrustedText text={r.title} />
                    {chosen && <Badge>선택됨</Badge>}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <UntrustedText as="p" text={r.summary} />
                  <p>
                    <span className="font-medium">차별화: </span>
                    <UntrustedText text={r.differentiation} />
                  </p>
                  {r.reasons.length > 0 && (
                    <ul className="list-disc space-y-0.5 pl-5">
                      {r.reasons.map((x, i) => (
                        <li key={i}><UntrustedText text={x} /></li>
                      ))}
                    </ul>
                  )}
                  {r.risks && (
                    <p className="text-muted-foreground">
                      <span className="font-medium">위험: </span>
                      <UntrustedText text={r.risks} />
                    </p>
                  )}
                  {r.overlap_warning.length > 0 && (
                    <p role="status" className="rounded-md border border-warning/60 p-2 text-warning">
                      자기 중복 경고: 이 추천도 {r.overlap_warning.length}건의 기존 과제와 가깝습니다 ({r.overlap_warning.join(", ")}).
                    </p>
                  )}
                </CardContent>
                <CardFooter>
                  <Button size="sm" variant="outline" onClick={() => openPreview(r.index)} disabled={loading !== null}>
                    {loading === r.index ? "불러오는 중…" : "미리보기"}
                  </Button>
                </CardFooter>
              </Card>
            </li>
          );
        })}
      </ul>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onClick={onProceedOriginal}>
          원래 아이디어로 진행
        </Button>
      </div>
      <Dialog
        open={preview !== null}
        onClose={() => setPreview(null)}
        title="추천 적용 미리보기"
        description="바뀌는 칸만 보여 줍니다. 확정하면 입력에 채워지고 ① 화면에서 고칠 수 있습니다."
        footer={
          <>
            <Button variant="outline" onClick={() => setPreview(null)}>
              취소
            </Button>
            <Button
              onClick={() => {
                if (preview) onChoose(preview.index, preview);
                setPreview(null);
              }}
            >
              확정
            </Button>
          </>
        }
      >
        {preview && (
          <dl className="space-y-3 text-sm">
            {(preview.changed.length ? preview.changed : Object.keys(preview.after)).map((k) => (
              <div key={k} className="rounded-md border p-3">
                <dt className="font-medium">{FIELD_LABELS[k] ?? k}</dt>
                <dd className="mt-1 grid gap-2 sm:grid-cols-2">
                  <div>
                    <p className="text-xs text-muted-foreground">이전</p>
                    <UntrustedText as="p" text={preview.before[k] || "(비어 있음)"} />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">이후</p>
                    <UntrustedText as="p" text={preview.after[k] || "(비어 있음)"} className="diff-ins" />
                  </div>
                </dd>
              </div>
            ))}
          </dl>
        )}
      </Dialog>
    </section>
  );
}
