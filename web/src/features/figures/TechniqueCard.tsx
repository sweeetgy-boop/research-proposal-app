/** [11] 분석 기법 추천 그림 — "추천" 배지·이유 한 줄·[넣기 확정]·[필요 없음]·[다른 기법으로 바꾸기],
 *  예비 평가 안내·항목 출처, 필요 없다고 한 추천(접힘·다시 넣기), 마지막 추천 결과·[다시 시도].
 *  모든 동작은 새 버전을 만든다(버전 비교의 "변경 n건"에 들어간다). 이유·항목 글자는 LLM 출력(비신뢰). */
import * as React from "react";
import { Check, Lightbulb, RefreshCw, Repeat, Undo2, X } from "lucide-react";
import type { FigureV2 } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { ProblemBanner } from "@/components/ProblemBanner";
import { UntrustedText } from "@/components/UntrustedText";
import { sectionTitle } from "@/lib/sections";
import { cn } from "@/lib/utils";
import { useFigureActionV2, useFiguresV2, useRetryTechniques } from "./api";

interface ActProps {
  runId: string;
  figure: FigureV2;
  baseVersion: number;
  disabled?: boolean;
  /** 조회 화면 — 배지·이유만, 버튼 없음 */
  readOnly?: boolean;
  onApplied: (version: number) => void;
}

/** 카드 안 추천 패널 — 결정 전이면 [넣기 확정]·[필요 없음], 언제든 [다른 기법으로 바꾸기]. */
export function RecommendationPanel({
  runId,
  figure,
  baseVersion,
  disabled,
  readOnly,
  onApplied,
}: ActProps) {
  const act = useFigureActionV2(runId);
  const [swap, setSwap] = React.useState(false);
  const rec = figure.recommendation;
  if (!rec) return null;
  const off = !!disabled || act.isPending;
  const run = async (action: "accept" | "dismiss") => {
    try {
      const out = await act.mutateAsync({
        fid: figure.id,
        body: { action, base_version: baseVersion },
      });
      onApplied(out.version);
    } catch {
      /* banner */
    }
  };
  const headingId = `rec-h-${figure.id}`;
  return (
    <section
      aria-labelledby={headingId}
      className="space-y-2 rounded border border-info/50 bg-info/5 p-2 text-sm"
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <Lightbulb className="size-4 text-info" aria-hidden="true" />
        <h5 id={headingId} className="font-semibold">
          추천 — {rec.technique_label}
        </h5>
        <Badge
          variant={
            rec.status === "pending"
              ? "warning"
              : rec.status === "accepted"
                ? "success"
                : "outline"
          }
        >
          {rec.status_label}
        </Badge>
      </div>
      <p className="text-xs">
        <span className="text-muted-foreground">이 제안에 맞는 이유: </span>
        <UntrustedText text={rec.reason} />
      </p>
      {rec.swapped_from_label && (
        <p className="text-xs text-muted-foreground">
          {rec.swapped_from_label} 대신 고른 기법입니다.
        </p>
      )}
      {rec.status === "pending" && (
        <p className="text-xs text-muted-foreground">
          결정하지 않고 마무리하면 제안서에 들어갑니다.
        </p>
      )}
      {!readOnly && (
        <div className="flex flex-wrap gap-1">
          {rec.status !== "accepted" && (
            <Button
              size="sm"
              onClick={() => run("accept")}
              disabled={off}
              aria-label={`${figure.label} 넣기 확정`}
            >
              <Check aria-hidden="true" />
              넣기 확정
            </Button>
          )}
          <Button
            size="sm"
            variant="outline"
            onClick={() => run("dismiss")}
            disabled={off}
            aria-label={`${figure.label} 필요 없음`}
          >
            <X aria-hidden="true" />
            필요 없음
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setSwap(true)}
            disabled={off}
            aria-label={`${figure.label} 다른 기법으로 바꾸기`}
          >
            <Repeat aria-hidden="true" />
            다른 기법으로 바꾸기
          </Button>
        </div>
      )}
      <ProblemBanner error={swap ? null : act.error} />
      {swap && (
        <SwapDialog
          runId={runId}
          figure={figure}
          baseVersion={baseVersion}
          onClose={() => setSwap(false)}
          onApplied={onApplied}
        />
      )}
    </section>
  );
}

/** 기법 그림의 예비 평가 안내·항목 출처 (본문 문장·제안 입력·근거 자료). */
export function TechniqueDetails({ figure }: { figure: FigureV2 }) {
  if (figure.kind !== "technique") return null;
  const rows = figure.provenance ?? [];
  return (
    <div className="space-y-1 text-xs">
      {figure.prelim_note && (
        <p className="text-muted-foreground">
          {figure.family_label ? `${figure.family_label} · ` : ""}
          {figure.prelim_note} — 등급·평가 기호는 제안 내용을 근거로 한
          판단입니다.
        </p>
      )}
      {rows.length > 0 && (
        <details>
          <summary className="cursor-pointer text-muted-foreground">
            항목 출처 {rows.length}개
          </summary>
          <ul className="mt-1 space-y-0.5 pl-1">
            {rows.map((r, i) => (
              <li key={i} className="flex flex-wrap gap-x-1">
                {r.group && <span className="font-medium">{r.group}</span>}
                <UntrustedText text={r.text} />
                {r.rating && (
                  <span className="text-muted-foreground">({r.rating})</span>
                )}
                {r.amount && (
                  <span className="text-muted-foreground">· {r.amount}</span>
                )}
                <span className="text-muted-foreground">
                  ← {sourceLabel(r)}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function sourceLabel(r: NonNullable<FigureV2["provenance"]>[number]): string {
  if (r.source_kind === "sentence" && r.section)
    return `${sectionTitle(r.section)} 문장 ${r.sentence_no ?? ""}`.trim();
  return r.source_label;
}

/** [다른 기법으로 바꾸기] — 20개 기법 중 하나를 골라 다시 분석·그림 */
function SwapDialog({
  runId,
  figure,
  baseVersion,
  onClose,
  onApplied,
}: Omit<ActProps, "disabled" | "readOnly"> & { onClose: () => void }) {
  const list = useFiguresV2(runId);
  const act = useFigureActionV2(runId);
  const [pick, setPick] = React.useState<string>("");
  const busy = act.isPending;
  const catalog = (list.data?.technique_catalog ?? []).filter(
    (t) => t.key !== figure.technique,
  );
  const submit = async () => {
    try {
      const out = await act.mutateAsync({
        fid: figure.id,
        body: { action: "swap", technique: pick, base_version: baseVersion },
      });
      onClose();
      onApplied(out.version);
    } catch {
      /* banner */
    }
  };
  return (
    <Dialog
      open
      onClose={() => !busy && onClose()}
      title={`${figure.label} — 다른 기법으로 바꾸기`}
      description="고른 기법으로 제안 내용을 다시 분석해 새로 그립니다 (같은 자리, 결정 전). 맞지 않으면 그 사유를 보여 줍니다."
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            취소
          </Button>
          <Button onClick={submit} disabled={busy || !pick}>
            {busy ? "분석하는 중…" : "바꾸기"}
          </Button>
        </>
      }
    >
      {list.isLoading && (
        <p className="text-sm text-muted-foreground">
          기법 목록을 불러오는 중…
        </p>
      )}
      <fieldset className="space-y-1" disabled={busy}>
        <legend className="text-sm font-medium">분석 기법</legend>
        <div
          role="radiogroup"
          aria-label="분석 기법"
          className="grid max-h-80 gap-1 overflow-y-auto"
        >
          {catalog.map((t) => {
            const on = pick === t.key;
            return (
              <label
                key={t.key}
                className={cn(
                  "flex cursor-pointer flex-col rounded-md border px-2.5 py-1.5 text-sm has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring",
                  on ? "border-primary bg-primary/10" : "hover:bg-accent",
                )}
              >
                <span className="flex items-center gap-2">
                  <input
                    type="radio"
                    name={`swap-${figure.id}`}
                    value={t.key}
                    checked={on}
                    onChange={() => setPick(t.key)}
                  />
                  <span className="font-medium">{t.label}</span>
                  <span className="text-xs text-muted-foreground">
                    {t.family_label}
                  </span>
                </span>
                <span className="pl-6 text-xs text-muted-foreground">
                  {t.fits}
                </span>
              </label>
            );
          })}
        </div>
      </fieldset>
      <ProblemBanner error={act.error ?? list.error} className="mt-3" />
    </Dialog>
  );
}

/** 섹션 아래 접힌 "필요 없다고 한 추천" — [다시 넣기]. */
export function DismissedRecommendations({
  runId,
  figures,
  baseVersion,
  disabled,
  readOnly,
  onApplied,
}: {
  runId: string;
  figures: FigureV2[];
  baseVersion: number;
  disabled?: boolean;
  readOnly?: boolean;
  onApplied: (version: number) => void;
}) {
  const act = useFigureActionV2(runId);
  if (figures.length === 0) return null;
  const restore = async (fid: string) => {
    try {
      const out = await act.mutateAsync({
        fid,
        body: { action: "restore", base_version: baseVersion },
      });
      onApplied(out.version);
    } catch {
      /* banner */
    }
  };
  return (
    <details className="rounded border border-dashed p-2 text-sm">
      <summary className="cursor-pointer text-muted-foreground">
        필요 없다고 한 추천 그림 {figures.length}장
      </summary>
      <ul className="mt-2 space-y-2">
        {figures.map((f) => (
          <li key={f.id} className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{f.label}</span>
            {f.recommendation && (
              <UntrustedText
                text={f.recommendation.reason}
                className="text-xs text-muted-foreground"
              />
            )}
            {!readOnly && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => restore(f.id)}
                disabled={!!disabled || act.isPending}
                aria-label={`${f.label} 다시 넣기`}
              >
                <Undo2 aria-hidden="true" />
                다시 넣기
              </Button>
            )}
          </li>
        ))}
      </ul>
      <ProblemBanner error={act.error} className="mt-2" />
    </details>
  );
}

/** 마지막 분석 기법 추천 결과 — 빈 결과도 사유를 보이고 [다시 시도]. 추천했으면 한 줄만. */
export function TechniqueStatus({
  runId,
  baseVersion,
  disabled,
  onApplied,
}: {
  runId: string;
  baseVersion: number;
  disabled?: boolean;
  onApplied: (version: number) => void;
}) {
  const list = useFiguresV2(runId);
  const retry = useRetryTechniques(runId);
  const [note, setNote] = React.useState<string | null>(null);
  const outcome = retry.data?.techniques ?? list.data?.techniques ?? null;
  if (!outcome) return null;
  const empty = outcome.status !== "recommended";
  const again = async () => {
    setNote(null);
    try {
      const out = await retry.mutateAsync({ base_version: baseVersion });
      if (out.created && typeof out.version === "number")
        onApplied(out.version);
      else setNote("새 추천 그림은 없습니다.");
    } catch {
      /* banner */
    }
  };
  return (
    <div
      className="flex flex-wrap items-center gap-2 text-xs"
      role="status"
      aria-live="polite"
    >
      <Badge
        variant={
          empty
            ? outcome.status === "failed"
              ? "destructive"
              : "outline"
            : "info"
        }
      >
        분석 기법 추천: {outcome.status_label}
      </Badge>
      <UntrustedText text={outcome.message} className="text-muted-foreground" />
      {empty && outcome.can_retry && (
        <Button
          size="sm"
          variant="outline"
          onClick={again}
          disabled={!!disabled || retry.isPending}
        >
          <RefreshCw aria-hidden="true" />
          {retry.isPending ? "다시 고르는 중…" : "다시 시도"}
        </Button>
      )}
      {note && <span className="text-muted-foreground">{note}</span>}
      <ProblemBanner error={retry.error} />
    </div>
  );
}
