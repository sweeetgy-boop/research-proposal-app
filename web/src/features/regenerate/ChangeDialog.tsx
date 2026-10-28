import { Loader2 } from "lucide-react";
import type { RegenerateMode, RequestPreviewOut } from "@/api/types";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ProblemBanner } from "@/components/ProblemBanner";

export interface ChangeDialogProps {
  open: boolean;
  preview: RequestPreviewOut | null;
  busy: boolean;
  error: unknown;
  onClose: () => void;
  onViewOnly: () => void;
  onRegenerate: (mode: RegenerateMode) => void;
}

/** 초안이 있는 run 에서 ①·② 를 바꿔 저장할 때 — 세 가지 중 하나를 고른다 (항목 17).
 *  다시 쓰기는 둘 다 새 버전을 만들고 기존 초안은 [버전·비교]에 이전 버전으로 남는다. */
export function ChangeDialog({ open, preview, busy, error, onClose, onViewOnly, onRegenerate }: ChangeDialogProps) {
  if (!open || !preview) return null;
  const none = preview.sections.length === 0;
  return (
    <Dialog
      open
      onClose={busy ? () => undefined : onClose}
      modalOnly={busy}
      title="바뀐 입력을 초안에 반영할까요?"
      description={`초안 v${preview.version} 이 있습니다. 근거 자료는 처음 검색한 것을 그대로 씁니다.`}
      footer={
        <>
          <Button variant="outline" onClick={onViewOnly} disabled={busy}>
            보기만 하고 돌아가기
          </Button>
          {none ? (
            <Button variant="secondary" onClick={() => onRegenerate("sections")} disabled={busy}>
              입력만 저장
            </Button>
          ) : (
            <Button variant="secondary" onClick={() => onRegenerate("sections")} disabled={busy || !preview.can_regenerate}>
              바뀐 내용과 관련된 섹션만 다시 쓰기(새 버전)
            </Button>
          )}
          <Button onClick={() => onRegenerate("all")} disabled={busy || !preview.can_regenerate}>
            초안 전체 다시 생성(새 버전, 기존은 이전 버전으로 보존)
          </Button>
        </>
      }
    >
      <div className="space-y-4 text-sm">
        <section aria-labelledby="chg-fields">
          <h3 id="chg-fields" className="mb-1 font-medium">바뀐 입력</h3>
          <ul className="flex flex-wrap gap-1.5">
            {preview.fields.map((f) => (
              <li key={f.field}>
                <Badge variant="secondary">{f.label}</Badge>
              </li>
            ))}
          </ul>
        </section>
        <section aria-labelledby="chg-sections">
          <h3 id="chg-sections" className="mb-1 font-medium">
            관련 섹션 {preview.sections.length}개 <span className="font-normal text-muted-foreground">(전체 {preview.all_sections}개)</span>
          </h3>
          {none ? (
            <p className="text-muted-foreground">바뀐 칸은 양식 칸(제안부서·예산)에만 들어가 다시 쓸 섹션이 없습니다. [입력만 저장]으로 마무리 때 반영됩니다.</p>
          ) : (
            <ul className="list-disc space-y-0.5 pl-5">
              {preview.sections.map((s) => (
                <li key={s.key}>{s.title}</li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-xs text-muted-foreground">
            관련 섹션만 다시 쓰면 제안자가 고치거나 적은 문장은 그 자리에 둡니다. 전체 다시 생성은 모든 섹션을 새로 씁니다.
          </p>
        </section>
        {!preview.can_regenerate && preview.reason && (
          <p role="status" className="rounded-md border border-warning/60 p-2 text-warning">
            {preview.reason}
          </p>
        )}
        {busy && (
          <p role="status" className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            다시 쓰는 중… 섹션 수에 따라 1분 안팎 걸립니다.
          </p>
        )}
        <ProblemBanner error={error} />
      </div>
    </Dialog>
  );
}
