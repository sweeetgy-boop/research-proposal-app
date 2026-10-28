import { GitBranch } from "lucide-react";
import type { Differentiation } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { UntrustedText } from "@/components/UntrustedText";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { tierLabel } from "@/lib/tiers";

export function DifferentiationPanel({
  diff,
  loading,
  onRequest,
  onPick,
  picked,
  similarCount,
}: {
  /** [유사함] 으로 고른 과제 수 (레인 A) — 없으면 활용 제안 대신 안내 */
  similarCount?: number;
  diff: (Differentiation & { skipped_label?: string | null }) | null | undefined;
  loading: boolean;
  onRequest: () => void;
  onPick: (text: string) => void;
  picked: string;
}) {
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <GitBranch className="size-5" aria-hidden="true" />
          유사과제 활용·차별화 제안
        </h2>
        <Button variant="outline" size="sm" onClick={onRequest} disabled={loading || similarCount === 0}>
          {loading ? "받는 중…" : diff ? "다시 받기" : "차별화 제안 받기"}
        </Button>
      </div>
      {loading && <SkeletonBlock lines={3} />}
      {!loading && diff && diff.items.length === 0 && (
        <p className="text-sm text-muted-foreground">
          {diff.skipped_label ?? "제안 항목이 없습니다. 모델이 항목을 만들지 못했습니다 — 다시 받기를 누르십시오."}
        </p>
      )}
      {!loading && diff && diff.items.length > 0 && (
        <ul className="grid gap-3">
          {diff.items.map((it) => (
            <li key={it.doc_id}>
              <Card>
                <CardHeader>
                  <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                    <UntrustedText text={it.title} />
                    <Badge variant="secondary">{tierLabel({ tier: it.tier })}</Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <p><span className="font-medium">겹치는 부분: </span><UntrustedText text={it.overlap_summary} /></p>
                  <p><span className="font-medium">이어받을 것: </span><UntrustedText text={it.build_on} /></p>
                  <ul className="space-y-1">
                    {it.differentiation.map((d, i) => (
                      <li key={i} className="flex items-start justify-between gap-2 rounded-md border p-2">
                        <UntrustedText text={d} />
                        <Button size="sm" variant={picked === d ? "default" : "outline"} onClick={() => onPick(d)} aria-pressed={picked === d}>
                          {picked === d ? "선택됨" : "이 방향 선택"}
                        </Button>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
      {!loading && !diff && (
        <p className="text-sm text-muted-foreground">
          {similarCount === 0
            ? "유사함으로 고른 과제가 없어 활용 제안은 건너뜁니다. 아래 차별화 과제안이 아이디어와 관련 연구로 방향을 제안합니다."
            : "[유사함] 으로 고른 과제만으로 활용·차별화 방향을 받습니다."}
        </p>
      )}
    </section>
  );
}
