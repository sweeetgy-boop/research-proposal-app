import * as React from "react";
import { ImagePlus } from "lucide-react";
import type { FigureKind } from "@/api/types";
import { useAddFigure } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { ProblemBanner } from "@/components/ProblemBanner";
import { SECTION_TITLES } from "@/lib/sections";
import { cn } from "@/lib/utils";
import { FIGURE_KINDS, KIND_LABELS, KIND_SECTION } from "./model";

export interface AddFigureDialogProps {
  runId: string;
  baseVersion: number;
  disabled?: boolean;
  onApplied: (version: number) => void;
}

const SECTIONS = Object.keys(SECTION_TITLES).filter((k) => k !== "title");

/** [다른 그림 추가] 버튼 + 대화상자 — 종류(6)·넣을 섹션을 고르면 새 버전에 그림이 생긴다. */
export function AddFigureDialog({ runId, baseVersion, disabled, onApplied }: AddFigureDialogProps) {
  const add = useAddFigure(runId);
  const [open, setOpen] = React.useState(false);
  const [kind, setKind] = React.useState<FigureKind>("concept");
  const [section, setSection] = React.useState<string>(KIND_SECTION.concept);
  const busy = add.isPending;

  const pick = (k: FigureKind) => {
    setKind(k);
    setSection(KIND_SECTION[k]);
  };
  const close = () => {
    if (busy) return;
    setOpen(false);
    add.reset();
  };
  const submit = async () => {
    try {
      const out = await add.mutateAsync({ kind, section, base_version: baseVersion });
      setOpen(false);
      add.reset();
      onApplied(out.version);
    } catch {
      /* banner */
    }
  };

  return (
    <>
      <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)} disabled={disabled}>
        <ImagePlus aria-hidden="true" />
        다른 그림 추가
      </Button>
      {open && (
        <Dialog
          open
          onClose={close}
          title="다른 그림 추가"
          description="그림 종류와 넣을 섹션을 고르십시오. 그림은 새 버전으로 저장됩니다."
          footer={
            <>
              <Button variant="outline" onClick={close} disabled={busy}>
                취소
              </Button>
              <Button onClick={submit} disabled={busy}>
                {busy ? "만드는 중…" : "추가"}
              </Button>
            </>
          }
        >
          <fieldset className="space-y-2" disabled={busy}>
            <legend className="text-sm font-medium">그림 종류</legend>
            <div role="radiogroup" aria-label="그림 종류" className="grid gap-1 sm:grid-cols-2">
              {FIGURE_KINDS.map((k) => {
                const on = kind === k;
                return (
                  <label
                    key={k}
                    className={cn(
                      "flex min-h-9 cursor-pointer items-center gap-2 rounded-md border px-2.5 text-sm has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring",
                      on ? "border-primary bg-primary text-primary-foreground" : "hover:bg-accent",
                    )}
                  >
                    <input type="radio" name="figure-kind" value={k} checked={on} onChange={() => pick(k)} className="sr-only" />
                    {KIND_LABELS[k]}
                  </label>
                );
              })}
            </div>
          </fieldset>
          <div className="mt-4 space-y-1">
            <Label htmlFor="figure-section">넣을 섹션</Label>
            <Select id="figure-section" value={section} onChange={(e) => setSection(e.target.value)} disabled={busy}>
              {SECTIONS.map((k) => (
                <option key={k} value={k}>
                  {SECTION_TITLES[k]}
                </option>
              ))}
            </Select>
          </div>
          <ProblemBanner error={add.error} className="mt-3" />
        </Dialog>
      )}
    </>
  );
}
