import * as React from "react";
import { History, RotateCcw } from "lucide-react";
import { useRunContext } from "./useRunContext";
import { useDiff, useRestore, useVersions } from "@/api/hooks";
import type { VersionMeta } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { VirtualList } from "@/components/VirtualList";
import { DiffView } from "@/features/versions/DiffView";
import { UntrustedText } from "@/components/UntrustedText";
import { sectionTitle } from "@/lib/sections";
import { formatDate } from "@/lib/utils";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

const EDITABLE = new Set(["drafted", "editing", "final_reviewed"]);

export default function Versions() {
  const { run, refetch } = useRunContext();
  const id = run.run_id;
  const q = useVersions(id);
  const versions = q.data?.versions ?? [];
  const latest = versions[versions.length - 1]?.version ?? null;
  const [from, setFrom] = React.useState<number | null>(null);
  const [to, setTo] = React.useState<number | null>(null);
  const a = from ?? (versions.length > 1 ? (versions[versions.length - 2]?.version ?? null) : null);
  const b = to ?? latest;
  const diff = useDiff(id, a, b);
  const restore = useRestore(id);
  const [confirm, setConfirm] = React.useState<number | null>(null);
  const { toast } = useToast();
  const canRestore = EDITABLE.has(run.status) && !run.legacy;

  const doRestore = async () => {
    if (confirm === null) return;
    try {
      const v = await restore.mutateAsync(confirm);
      toast(`v${confirm} 내용으로 v${v.version} 을 만들었습니다.`, "success");
      setConfirm(null);
      refetch();
    } catch {
      /* banner */
    }
  };

  if (q.isPending) return <SkeletonBlock lines={6} />;
  if (q.error) return <ProblemBanner error={q.error} onRetry={() => q.refetch()} />;

  const renderRow = (v: VersionMeta) => (
    <div className={cn("flex flex-wrap items-start gap-3 border-b px-2 py-3 text-sm", v.version === latest && "bg-accent/40")}>
      <span className="w-10 font-mono font-semibold">v{v.version}</span>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="secondary">{v.origin_label}</Badge>
          {v.version === latest && <Badge>현재</Badge>}
          {v.reverted_from && <span className="text-xs text-muted-foreground">v{v.reverted_from} 에서 복원</span>}
          {v.based_on_review && <span className="text-xs text-muted-foreground">검토 {v.based_on_review}차 반영</span>}
          <span className="text-xs text-muted-foreground">{formatDate(v.created_at)}</span>
        </div>
        {v.note && <UntrustedText as="p" text={v.note} className="text-muted-foreground" />}
        <p className="text-xs text-muted-foreground">
          문장 {v.sentences ?? "—"} · 알림 {v.alerts} · 남은 메모 {v.open_annotations}
          {v.changed_sections.length > 0 && ` · 바뀐 섹션: ${v.changed_sections.map(sectionTitle).join(", ")}`}
        </p>
      </div>
      <div className="flex gap-1">
        <Button size="sm" variant="outline" onClick={() => { setFrom(v.version); setTo(latest); }} aria-label={`v${v.version} 을 현재와 비교`}>
          비교
        </Button>
        {v.version !== latest && (
          <Button size="sm" variant="ghost" onClick={() => setConfirm(v.version)} disabled={!canRestore} aria-label={`v${v.version} 으로 복원`}>
            <RotateCcw aria-hidden="true" />
            복원
          </Button>
        )}
      </div>
    </div>
  );

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <section aria-labelledby="ver-h" className="min-w-0">
        <h2 id="ver-h" className="mb-2 flex items-center gap-2 text-lg font-semibold">
          <History className="size-5" aria-hidden="true" />
          버전 {versions.length}개
        </h2>
        <ProblemBanner error={restore.error} />
        <div className="rounded-lg border">
          <VirtualList items={versions} getKey={(v) => String(v.version)} estimate={96} renderRow={renderRow} as="div" ariaLabel="버전 목록" />
        </div>
      </section>
      <section aria-labelledby="diff-h" className="min-w-0 space-y-3">
        <h2 id="diff-h" className="text-lg font-semibold">비교</h2>
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <Label htmlFor="from">이전</Label>
            <Select id="from" value={a ?? ""} onChange={(e) => setFrom(Number(e.target.value))} className="w-28">
              {versions.map((v) => (
                <option key={v.version} value={v.version}>v{v.version}</option>
              ))}
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="to">이후</Label>
            <Select id="to" value={b ?? ""} onChange={(e) => setTo(Number(e.target.value))} className="w-28">
              {versions.map((v) => (
                <option key={v.version} value={v.version}>v{v.version}</option>
              ))}
            </Select>
          </div>
        </div>
        <div className="min-h-40">
          {a === null || b === null || a === b ? (
            <p className="text-sm text-muted-foreground">{versions.length < 2 ? "비교할 다른 버전이 아직 없습니다." : "서로 다른 두 버전을 고르십시오."}</p>
          ) : diff.isPending ? (
            <SkeletonBlock lines={5} />
          ) : diff.error ? (
            <ProblemBanner error={diff.error} onRetry={() => diff.refetch()} />
          ) : diff.data ? (
            <DiffView diff={diff.data} />
          ) : null}
        </div>
      </section>
      <Dialog
        open={confirm !== null}
        onClose={() => setConfirm(null)}
        title={`v${confirm} 으로 복원`}
        description="그 버전의 내용으로 새 버전을 만듭니다. 기존 버전은 지워지지 않습니다."
        footer={
          <>
            <Button variant="outline" onClick={() => setConfirm(null)}>취소</Button>
            <Button onClick={doRestore} disabled={restore.isPending}>{restore.isPending ? "복원 중…" : "복원"}</Button>
          </>
        }
      />
    </div>
  );
}
