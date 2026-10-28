import * as React from "react";
import { ImagePlus } from "lucide-react";
import type { FigureKindV2 } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { ProblemBanner } from "@/components/ProblemBanner";
import { SECTION_TITLES } from "@/lib/sections";
import { cn } from "@/lib/utils";
import { FIGURE_KINDS, KIND_LABELS, KIND_SECTION } from "./model";
import { useAddFigureAi, useFiguresV2 } from "./api";
import { AiCancelledNote, AiWaiting } from "@/components/AiWaiting";
import { TechniqueStatus } from "./TechniqueCard";

export interface AddFigureDialogProps {
  runId: string;
  baseVersion: number;
  disabled?: boolean;
  onApplied: (version: number) => void;
}

const SECTIONS = Object.keys(SECTION_TITLES).filter((k) => k !== "title");

/** [다른 그림 추가] 버튼 + 대화상자 — 종류(8, 분석 기법은 20개 중 하나)·넣을 섹션을 고르면 새 버전에 그림이
 *  생긴다. 옆에 마지막 분석 기법 추천 결과(빈 결과도 사유)와 [다시 시도]. */
export function AddFigureDialog({ runId, baseVersion, disabled, onApplied }: AddFigureDialogProps) {
  const add = useAddFigureAi(runId);
  const list = useFiguresV2(runId);
  const [open, setOpen] = React.useState(false);
  const [kind, setKind] = React.useState<FigureKindV2>("as_is_to_be");
  const [section, setSection] = React.useState<string>(KIND_SECTION.as_is_to_be);
  const [technique, setTechnique] = React.useState<string>("");
  const busy = add.pending;
  const catalog = list.data?.technique_catalog ?? [];

  const pick = (k: FigureKindV2) => {
    setKind(k);
    setSection(KIND_SECTION[k]);
  };
  const pickTechnique = (key: string) => {
    setTechnique(key);
    const row = catalog.find((t) => t.key === key);
    if (row) setSection(row.section);
  };
  const close = () => {
    if (busy) return;
    setOpen(false);
    add.reset();
  };
  const submit = async () => {
    const out = await add.run({ kind, section, base_version: baseVersion, ...(kind === "technique" ? { technique } : {}) });
    if (!out) return; // 취소(대화상자 그대로) 또는 오류(banner)
    setOpen(false);
    add.reset();
    onApplied(out.version);
  };

  return (
    <>
      <TechniqueStatus runId={runId} baseVersion={baseVersion} disabled={disabled} onApplied={onApplied} />
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
              <Button onClick={submit} disabled={busy || (kind === "technique" && !technique)}>
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
          {kind === "technique" && (
            <div className="mt-4 space-y-1">
              <Label htmlFor="figure-technique">분석 기법</Label>
              <Select id="figure-technique" value={technique} onChange={(e) => pickTechnique(e.target.value)} disabled={busy}>
                <option value="">기법을 고르십시오</option>
                {catalog.map((t) => (
                  <option key={t.key} value={t.key}>
                    {t.label} ({t.family_label})
                  </option>
                ))}
              </Select>
              {technique && <p className="text-xs text-muted-foreground">{catalog.find((t) => t.key === technique)?.fits}</p>}
            </div>
          )}
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
          <AiWaiting pending={add.pending} elapsed={add.elapsed} onCancel={add.cancel} what="그림 만들기" className="mt-3" />
          <AiCancelledNote show={add.cancelled} className="mt-3" />
          <ProblemBanner error={add.error} className="mt-3" />
        </Dialog>
      )}
    </>
  );
}
