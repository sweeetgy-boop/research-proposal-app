import * as React from "react";
import { Check, Image as ImageIcon, Info, MessageSquareText, Minus, Plus, RefreshCw, Type } from "lucide-react";
import type { FigureActionV2In, FigureV2 } from "@/api/types";
import { AiCancelledNote, AiWaiting } from "@/components/AiWaiting";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ProblemBanner } from "@/components/ProblemBanner";
import { UntrustedText } from "@/components/UntrustedText";
import { useFigureActionAi } from "./api";
import { figureAspect, figureName, imageSrc } from "./model";
import { RecommendationPanel, TechniqueDetails } from "./TechniqueCard";

export interface FigureCardProps {
  runId: string;
  figure: FigureV2;
  /** 동작의 base_version — 현재 버전 번호 */
  baseVersion: number;
  /** 모든 버튼 비활성 (편집 불가 상태·임시 편집 중·옛 버전) */
  disabled?: boolean;
  /** 조회 화면(초안 보기): [확인함] 만 남기고 수정 버튼은 숨긴다 */
  readOnly?: boolean;
  /** 옛 버전의 그림 — 이미지 주소에 ?version=N */
  version?: number | null;
  onApplied: (version: number) => void;
}

type Mode = null | "words" | "texts";
/** AI 를 부르는 동작 — 기다리는 동안 경과 초와 [취소] */
const AI_ACTIONS = new Set(["words", "regenerate", "swap"]);

/** 그림 한 장 — 이미지·캡션·배지·동작 버튼. 모든 동작은 새 버전을 만든다(409 는 카드 안에 표시). */
export function FigureCard({ runId, figure, baseVersion, disabled, readOnly, version, onApplied }: FigureCardProps) {
  const act = useFigureActionAi(runId);
  const [mode, setMode] = React.useState<Mode>(null);
  const [request, setRequest] = React.useState("");
  const [texts, setTexts] = React.useState<Record<string, string>>({});
  const [lastAction, setLastAction] = React.useState<string>("");
  const busy = act.pending;
  const off = !!disabled || busy;
  const headingId = `fig-h-${figure.id}`;
  const name = figureName(figure);
  const aspect = figureAspect(figure);

  const run = async (body: Omit<FigureActionV2In, "request"> & { request?: string }) => {
    setLastAction(body.action);
    const out = await act.run({ fid: figure.id, body: { request: "", base_version: baseVersion, ...body } });
    if (!out) return; // 취소(화면 그대로) 또는 오류(카드 안 banner)
    setMode(null);
    setRequest("");
    setTexts({});
    onApplied(out.version);
  };
  const waitingWhat = lastAction === "words" ? "그림 말로 고치기" : lastAction === "swap" ? "다른 기법 분석" : "그림 다시 만들기";
  const aiPending = busy && AI_ACTIONS.has(lastAction);

  const openTexts = () => {
    setTexts(Object.fromEntries(figure.texts.map((t) => [t.path, t.value])));
    setMode("texts");
  };
  const changedTexts = Object.fromEntries(
    figure.texts.filter((t) => texts[t.path] !== undefined && texts[t.path] !== t.value).map((t) => [t.path, texts[t.path] ?? ""]),
  );
  const nChanged = Object.keys(changedTexts).length;

  const cacheBust = figure.updated_at ?? (version !== undefined && version !== null ? String(version) : null);
  const src = imageSrc(figure.image_url, { version, v: cacheBust });
  const baselineSrc = imageSrc(figure.baseline_url, { version, v: cacheBust });

  return (
    <Card role="group" aria-labelledby={headingId} className={figure.included ? undefined : "opacity-75"}>
      <CardHeader className="gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <h4 id={headingId} className="text-sm font-semibold">
            {name}
          </h4>
          <Badge variant={figure.renderer === "baseline" ? "secondary" : "default"}>{figure.renderer_label}</Badge>
          {figure.confirmed ? <Badge variant="success">확인함</Badge> : <Badge variant="warning">확인 전</Badge>}
          {!figure.included && <Badge variant="outline">뺌</Badge>}
          {figure.error && (
            <Badge variant="destructive" className="whitespace-normal text-left">
              {figure.error_label ?? "그림 AI 호출이 실패해 기본 그림으로 넣었습니다."}
            </Badge>
          )}
        </div>
        {/* [23] 가로로 넓은 그림 — 그림 비율 그대로 카드 폭에 맞춘다 */}
        <img
          src={src}
          alt={figure.alt || name}
          loading="lazy"
          data-testid="figure-image"
          data-aspect={aspect}
          style={{ aspectRatio: aspect }}
          className="w-full rounded border bg-white object-contain"
        />
        {figure.fit?.note && <p className="text-xs text-muted-foreground">{figure.fit.note}</p>}
        <UntrustedText as="p" text={figure.caption} className="text-sm" />
        {figure.source_caption && <UntrustedText as="p" text={figure.source_caption} className="text-xs text-muted-foreground" />}
        {figure.last_change && figure.last_change.summary.length > 0 && (
          <section aria-labelledby={`${headingId}-change`} className="rounded border bg-muted/40 p-2 text-xs">
            <h5 id={`${headingId}-change`} className="font-semibold">
              바뀐 내용{figure.last_change.kind === "style" ? " (모양만)" : ""}
            </h5>
            <ul className="mt-1 list-disc space-y-0.5 pl-4">
              {figure.last_change.summary.map((line, i) => (
                <li key={i}>
                  <UntrustedText text={line} />
                </li>
              ))}
            </ul>
          </section>
        )}
        {figure.notice && (
          <p className="flex items-start gap-1 text-xs text-muted-foreground">
            <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            <span>{figure.notice}</span>
          </p>
        )}
      </CardHeader>
      <CardContent className="space-y-2">
        <ProblemBanner error={mode === null ? act.error : null} />
        <AiCancelledNote show={act.cancelled && mode === null} />
        <TechniqueDetails figure={figure} />
        <RecommendationPanel runId={runId} figure={figure} baseVersion={baseVersion} disabled={disabled} readOnly={readOnly} onApplied={onApplied} />
        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground">밑그림 보기</summary>
          <img src={baselineSrc} alt={`${name} 밑그림`} loading="lazy" style={{ aspectRatio: aspect }} className="mt-2 w-full rounded border bg-white object-contain" />
        </details>
      </CardContent>
      <CardFooter className="gap-1">
        {!figure.confirmed && (
          <Button size="sm" onClick={() => run({ action: "confirm" })} disabled={off} aria-label={`${name} 확인함`}>
            <Check aria-hidden="true" />
            확인함
          </Button>
        )}
        {!readOnly && (
          <>
            <Button size="sm" variant="outline" onClick={() => setMode("words")} disabled={off} aria-label={`${name} 말로 고치기`}>
              <MessageSquareText aria-hidden="true" />
              말로 고치기
            </Button>
            <Button size="sm" variant="outline" onClick={openTexts} disabled={off || figure.texts.length === 0} aria-label={`${name} 글자 고치기`}>
              <Type aria-hidden="true" />
              글자 고치기
            </Button>
            {figure.renderer !== "baseline" && (
              <Button size="sm" variant="outline" onClick={() => run({ action: "baseline" })} disabled={off} aria-label={`${name} 기본 그림으로`}>
                <ImageIcon aria-hidden="true" />
                기본 그림으로
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={() => run({ action: "regenerate" })} disabled={off} aria-label={`${name} 다시 만들기`}>
              <RefreshCw aria-hidden="true" />
              다시 만들기
            </Button>
            {figure.recommendation ? null : figure.included ? (
              <Button size="sm" variant="ghost" onClick={() => run({ action: "exclude" })} disabled={off} aria-label={`${name} 빼기`}>
                <Minus aria-hidden="true" />
                빼기
              </Button>
            ) : (
              <Button size="sm" variant="ghost" onClick={() => run({ action: "include" })} disabled={off} aria-label={`${name} 넣기`}>
                <Plus aria-hidden="true" />
                넣기
              </Button>
            )}
          </>
        )}
        {busy && !aiPending && (
          <span className="text-xs text-muted-foreground" role="status">
            그림 처리 중…
          </span>
        )}
        {mode === null && <AiWaiting pending={aiPending} elapsed={act.elapsed} onCancel={act.cancel} what={waitingWhat} />}
      </CardFooter>

      {mode === "words" && (
        <Dialog
          open
          onClose={() => setMode(null)}
          title={`${name} 말로 고치기`}
          description="바꾸고 싶은 점을 한두 문장으로 적으십시오 (500자). 글자·단계·순서를 바꾸는 요청은 그림 명세를 고친 뒤 밑그림에서 새로 그리고, 색·굵기·여백 같은 모양 요청은 명세는 그대로 두고 밑그림에서 다시 그립니다. 고친 그림은 다시 확인 전이 됩니다."
          footer={
            <>
              <Button variant="outline" onClick={() => setMode(null)} disabled={busy}>
                취소
              </Button>
              <Button onClick={() => run({ action: "words", request: request.trim() })} disabled={busy || request.trim().length === 0}>
                {busy ? "고치는 중…" : "고치기"}
              </Button>
            </>
          }
        >
          <div className="space-y-1">
            <Label htmlFor={`fig-words-${figure.id}`}>수정 요청</Label>
            <Textarea id={`fig-words-${figure.id}`} value={request} onChange={(e) => setRequest(e.target.value)} maxLength={500} rows={4} autoFocus />
            <p className="text-xs text-muted-foreground">{request.length}/500</p>
          </div>
          <AiWaiting pending={aiPending} elapsed={act.elapsed} onCancel={act.cancel} what={waitingWhat} className="mt-3" />
          <AiCancelledNote show={act.cancelled} className="mt-3" />
          <ProblemBanner error={act.error} className="mt-3" />
        </Dialog>
      )}

      {mode === "texts" && (
        <Dialog
          open
          onClose={() => setMode(null)}
          title={`${name} 글자 고치기`}
          description="그림 안 글자만 바꿉니다. 바뀐 칸만 보냅니다."
          footer={
            <>
              <Button variant="outline" onClick={() => setMode(null)} disabled={busy}>
                취소
              </Button>
              <Button onClick={() => run({ action: "texts", texts: changedTexts })} disabled={busy || nChanged === 0}>
                {busy ? "적용 중…" : `적용${nChanged ? ` (${nChanged})` : ""}`}
              </Button>
            </>
          }
        >
          <div className="space-y-3">
            {figure.texts.map((t, i) => {
              const inputId = `fig-text-${figure.id}-${i}`;
              return (
                <div key={t.path} className="space-y-1">
                  <Label htmlFor={inputId}>{t.label}</Label>
                  <Input id={inputId} value={texts[t.path] ?? ""} onChange={(e) => setTexts((s) => ({ ...s, [t.path]: e.target.value }))} maxLength={500} autoFocus={i === 0} />
                </div>
              );
            })}
          </div>
          <ProblemBanner error={act.error} className="mt-3" />
        </Dialog>
      )}
    </Card>
  );
}
