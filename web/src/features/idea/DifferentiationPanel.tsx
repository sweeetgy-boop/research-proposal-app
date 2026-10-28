import { GitBranch } from "lucide-react";
import { reasonLabel } from "@/lib/labels";
import type { Differentiation } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { UntrustedText } from "@/components/UntrustedText";
import { SkeletonBlock } from "@/components/ui/skeleton";

export function DifferentiationPanel({
  diff,
  loading,
  onRequest,
  onPick,
  picked,
}: {
  diff: Differentiation | null | undefined;
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
        <Button variant="outline" size="sm" onClick={onRequest} disabled={loading}>
          {loading ? "받는 중…" : diff ? "다시 받기" : "차별화 제안 받기"}
        </Button>
      </div>
      {loading && <SkeletonBlock lines={3} />}
      {!loading && diff && diff.items.length === 0 && (
        <p className="text-sm text-muted-foreground">
          제안 항목이 없습니다{diff.skipped_reason ? ` (${reasonLabel(diff.skipped_reason)})` : ""}. 차단·근접 유사과제가 없거나 모델이 항목을 만들지 못했습니다.
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
                    <Badge variant="secondary">{it.tier}</Badge>
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
        <p className="text-sm text-muted-foreground">차단 알림이 있으면 자동으로 받고, 근접 알림만 있으면 요청할 때 받습니다.</p>
      )}
    </section>
  );
}
