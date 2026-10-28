import { ListChecks } from "lucide-react";
import type { ChangesOut } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";

/** ④ [새 버전으로 저장] 뒤 묻는 창 — 변경 없음: "변경된 내용이 없습니다. 최종 검토로 넘어갈까요?" (새 버전 없음),
 *  변경 있음: 저장한 뒤 "최종 검토로 넘어갈까요?". [확인] → ⑤ 최종 검토, [취소] → 그대로. */
export function SaveVersionDialog({
  open,
  kind,
  savedVersion,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  /** none = 바뀐 것 없음 · saved = 새 버전 저장함 · already = 바뀐 것이 이미 버전으로 저장되어 있음 */
  kind: "none" | "saved" | "already";
  savedVersion?: number | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const body =
    kind === "none"
      ? "변경된 내용이 없습니다. 최종 검토로 넘어갈까요?"
      : kind === "saved"
        ? `v${savedVersion ?? ""} 으로 저장했습니다. 최종 검토로 넘어갈까요?`
        : `바뀐 내용은 이미 v${savedVersion ?? ""} 까지 저장되어 있습니다. 최종 검토로 넘어갈까요?`;
  return (
    <Dialog
      open={open}
      onClose={onCancel}
      title={kind === "none" ? "변경된 내용이 없습니다" : "저장했습니다"}
      footer={
        <>
          <Button variant="outline" onClick={onCancel}>
            취소
          </Button>
          <Button onClick={onConfirm}>확인</Button>
        </>
      }
    >
      <p className="text-sm">{body}</p>
      <p className="mt-2 text-xs text-muted-foreground">[확인] 은 ⑤ 최종 검토 화면으로 갑니다{kind === "none" ? " (새 버전을 만들지 않습니다)" : ""}. [취소] 는 이 화면에 남습니다.</p>
    </Dialog>
  );
}

/** "변경 n건" — 저장하지 않은 편집 + 마지막 검토 이후 바로 저장된 변경(그림·근거·정책 근거·보완 메모…) */
export function ChangeCount({ local, server }: { local: number; server: ChangesOut | null | undefined }) {
  const serverTotal = server?.total ?? 0;
  const total = local + serverTotal;
  const parts = [...(local ? [`저장 안 한 편집 ${local}`] : []), ...(server?.items ?? []).map((i) => `${i.label} ${i.count}`)];
  return (
    <span className="flex items-center gap-1 text-sm text-muted-foreground" aria-live="polite">
      <ListChecks className="size-4" aria-hidden="true" />
      <span>변경 {total}건</span>
      {parts.length > 0 && (
        <span className="hidden text-xs sm:inline" title={server ? `v${server.base_version} 이후` : undefined}>
          ({parts.join(" · ")})
        </span>
      )}
    </span>
  );
}
