import * as React from "react";
import { useNavigate } from "react-router";
import { SkipForward } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SaveVersionDialog } from "./SaveVersionFlow";

/** 초안 보기의 [수정 없이 최종 검토로] — 직접 수정의 "변경 없음 → 최종 검토" 와 같은 창(새 버전 없음, 항목 22). */
export function SkipEditButton({ runId, disabled }: { runId: string; disabled?: boolean }) {
  const [open, setOpen] = React.useState(false);
  const navigate = useNavigate();
  return (
    <>
      <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)} disabled={disabled}>
        <SkipForward aria-hidden="true" />
        수정 없이 최종 검토로
      </Button>
      <SaveVersionDialog
        open={open}
        kind="none"
        onCancel={() => setOpen(false)}
        onConfirm={() => {
          setOpen(false);
          navigate(`/runs/${runId}/final-review`);
        }}
      />
    </>
  );
}
