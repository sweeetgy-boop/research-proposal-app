import * as React from "react";
import { ExternalLink, Landmark, RefreshCw, Sparkles } from "lucide-react";
import type { PolicyCard, PolicyCardsOut, PolicyChoice, PolicyPolishOut } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { UntrustedText } from "@/components/UntrustedText";
import { AiCancelledNote, AiWaiting } from "@/components/AiWaiting";
import { DocRef } from "@/components/DocRef";
import { useAiCall } from "@/lib/useAiCall";
import { cn } from "@/lib/utils";
import { MODE_LABEL, NONE_CHOICE, choiceFromCard, choiceText, editedChoice, mergeCards, seenDocs } from "./model";

export interface PolicyCardsProps {
  /** 작성안 받기 — exclude: [다른 안 보기] 때 이미 본 문서 id. signal: [취소] */
  load: (exclude: string[], signal?: AbortSignal) => Promise<PolicyCardsOut>;
  /** [AI로 다듬기] */
  polish: (choice: PolicyChoice, text: string, signal?: AbortSignal) => Promise<PolicyPolishOut>;
  /** 지금 고른 것 (없으면 null) */
  value: PolicyChoice | null;
  /** 제안자가 확정한 것 — 안 하나·합친 안·고친 글·직접 작성·"정책 근거 없음" */
  onChoose: (choice: PolicyChoice) => void | Promise<void>;
  /** 고르는 중 저장 등 — 버튼을 막는다 */
  busy?: boolean;
  /** [직접 작성] 단추 — ④ 대화상자는 위에 따로 "직접 입력" 칸이 있어 숨긴다 */
  manual?: boolean;
}

function SourceLine({ s }: { s: PolicyCard["sources"][number] }) {
  const meta = [s.year ? `${s.year}년` : null, s.page].filter(Boolean).join(" · ");
  return (
    <li className="space-y-1 rounded border bg-muted/30 p-2 text-xs">
      <div className="flex flex-wrap items-center gap-1">
        <DocRef docRef={{ doc_id: s.doc_id, title: s.title, source: s.source, source_label: s.source_label, url: s.url, summary: s.quote }} compact />
        {meta && <span className="text-muted-foreground">({meta})</span>}
      </div>
      <blockquote className="border-l-2 pl-2 text-muted-foreground">
        <UntrustedText text={`“${s.quote}”`} />
      </blockquote>
      {s.url && (
        <a href={s.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline">
          원문 보기 <ExternalLink className="size-3" aria-hidden="true" />
          <span className="sr-only">(새 창, {s.title})</span>
        </a>
      )}
    </li>
  );
}

/** 정책적 중요도 작성안 — 정책 근거가 없을 때 수집 정책 자료에서 찾은 구간으로 쓴 안(방향별, 근거 겹침 없음).
 *  [이 안으로] · 두 안 합치기 · 고른 뒤 직접 수정 + [AI로 다듬기] · [직접 작성] · [정책 근거 없음으로 진행] · [다른 안 보기]. */
export function PolicyCards({ load, polish, value, onChoose, busy, manual = true }: PolicyCardsProps) {
  const [seen, setSeen] = React.useState<string[]>([]);
  const [merge, setMerge] = React.useState<string[]>([]);
  const [editing, setEditing] = React.useState<string | null>(null);
  const [polishNote, setPolishNote] = React.useState<string | null>(null);

  // 시간 제한 없이 기다린다 — "응답 기다리는 중 · 경과 n초" + [취소] (취소하면 이전 상태 그대로)
  const cardsCall = useAiCall((exclude: string[], signal) => load(exclude, signal));
  const polishCall = useAiCall((args: { choice: PolicyChoice; text: string }, signal) => polish(args.choice, args.text, signal));
  const data = cardsCall.data ?? null;
  const error = cardsCall.error;
  const loading = cardsCall.pending;
  const polishing = polishCall.pending;
  const runCards = cardsCall.run;
  const fetchCards = React.useCallback(
    async (exclude: string[]) => {
      const out = await runCards(exclude);
      if (out) {
        setSeen(seenDocs(out.cards, exclude));
        setMerge([]);
      }
    },
    [runCards],
  );

  React.useEffect(() => {
    void fetchCards([]);
  }, [fetchCards]);

  const cards = data?.cards ?? [];
  const toggleMerge = (id: string, on: boolean) => setMerge((m) => (on ? [...m.filter((x) => x !== id), id].slice(-2) : m.filter((x) => x !== id)));
  const doMerge = () => {
    const [a, b] = merge.map((id) => cards.find((c) => c.id === id)).filter(Boolean) as PolicyCard[];
    if (a && b) void onChoose(mergeCards(a, b));
  };
  const startEdit = () => {
    setPolishNote(null);
    setEditing(choiceText(value));
  };
  const doPolish = async () => {
    if (!value || editing === null) return;
    setPolishNote(null);
    const out = await polishCall.run({ choice: value, text: editing });
    if (!out) return; // 취소(이전 상태 그대로) 또는 오류(아래 한 줄 안내)
    if (out.choice && out.choice.sentences.length) {
      setEditing(choiceText(out.choice));
      setPolishNote(out.dropped ? `다듬은 문장 중 ${out.dropped}개는 근거·정책명·수치 검사에서 빠졌습니다.` : "다듬었습니다. 확인한 뒤 [고친 글 적용] 을 누르십시오.");
    } else {
      setPolishNote(`다듬지 못했습니다 — ${out.reason_label ?? "호출 실패"}. 다시 시도하거나 고친 글을 그대로 적용하십시오.`);
    }
  };
  const applyEdit = () => {
    if (editing === null) return;
    const next = editedChoice(value && value.mode !== "none" ? value : null, editing);
    if (!next.sentences.length) return;
    setEditing(null);
    void onChoose(next);
  };

  return (
    <section aria-labelledby="policy-cards-h" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="policy-cards-h" className="flex items-center gap-2 text-base font-semibold">
          <Landmark className="size-5" aria-hidden="true" />
          정책적 중요도 작성안
        </h3>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => fetchCards(seen)} disabled={loading || busy}>
            <RefreshCw aria-hidden="true" />
            다른 안 보기
          </Button>
          {manual && (
            <Button size="sm" variant="outline" onClick={() => { setPolishNote(null); setEditing(""); }} disabled={busy}>
              직접 작성
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => onChoose(NONE_CHOICE)} disabled={busy}>
            정책 근거 없음으로 진행
          </Button>
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        수집한 국토부 계획·공사 중장기 전략·감사 지적·정부 R&amp;D 공고에서 아이디어와 관련된 구간을 찾아, 인용한 구간 안에서만 쓴 안입니다(Argon, 실패하면 로컬 모델). 안마다 근거 문서가 겹치지 않습니다. 고른 안만 제안서 2-가-(1)에 들어갑니다.
      </p>

      {value && (
        <Alert variant={value.mode === "none" ? "warning" : "success"} role="status">
          <div className="flex-1 space-y-1">
            <AlertTitle>고른 정책 근거: {MODE_LABEL[value.mode]}</AlertTitle>
            {value.mode === "none" ? (
              <AlertDescription>정책적 중요도 칸은 비우지 않고 "정책 근거 확인 필요" 알림으로 남으며, 제출 전 점검에서 다시 표시됩니다.</AlertDescription>
            ) : (
              <>
                <ul className="space-y-0.5 text-sm">
                  {value.sentences.map((s, i) => (
                    <li key={i}>
                      ○ <UntrustedText text={s.text} />
                      {s.evidence.length > 0 && <Badge variant="outline" className="ml-1">근거 {s.evidence.length}</Badge>}
                    </li>
                  ))}
                </ul>
                {editing === null && (
                  <Button size="sm" variant="outline" className="mt-1" onClick={startEdit} disabled={busy}>
                    직접 수정
                  </Button>
                )}
              </>
            )}
          </div>
        </Alert>
      )}

      {editing !== null && (
        <div className="space-y-2 rounded-lg border bg-card p-3">
          <Label htmlFor="policy-edit">{value && value.mode !== "none" ? "고른 안 고치기 (줄마다 한 문장)" : "정책적 중요도 직접 작성 (줄마다 한 문장)"}</Label>
          <Textarea id="policy-edit" rows={4} maxLength={2000} value={editing} onChange={(e) => setEditing(e.target.value)} />
          {polishNote && (
            <p className="text-xs text-muted-foreground" role="status" aria-live="polite">
              {polishNote}
            </p>
          )}
          <AiWaiting pending={polishing} elapsed={polishCall.elapsed} onCancel={polishCall.cancel} what="AI로 다듬기" />
          <AiCancelledNote show={polishCall.cancelled} />
          {polishCall.error ? (
            <p className="text-xs text-destructive" role="alert">
              다듬지 못했습니다 — 호출 실패. 다시 시도하거나 고친 글을 그대로 적용하십시오.
            </p>
          ) : null}
          <div className="flex flex-wrap justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>
              취소
            </Button>
            {value && value.mode !== "none" && (
              <Button size="sm" variant="secondary" onClick={doPolish} disabled={polishing || !editing.trim()}>
                <Sparkles aria-hidden="true" />
                {polishing ? "다듬는 중…" : "AI로 다듬기"}
              </Button>
            )}
            <Button size="sm" onClick={applyEdit} disabled={!editing.trim() || busy}>
              고친 글 적용
            </Button>
          </div>
        </div>
      )}

      <ProblemBanner error={error} onRetry={() => fetchCards([])} />
      <AiCancelledNote show={cardsCall.cancelled} />
      {loading ? (
        <div aria-busy="true" className="space-y-2">
          <AiWaiting pending elapsed={cardsCall.elapsed} onCancel={cardsCall.cancel} what="정책적 중요도 작성안" />
          <SkeletonBlock lines={4} />
        </div>
      ) : data && data.status !== "ok" ? (
        <Alert variant={data.status === "empty" ? "info" : "warning"} role="status">
          <div className="flex-1">
            <AlertTitle>작성안이 없습니다 — {data.status === "empty" ? "해당 없음" : data.status === "filtered" ? "규칙에 걸러짐" : "호출 실패"}</AlertTitle>
            <AlertDescription>
              {data.status_label}
              {data.reason_label && data.status === "failed" ? ` (${data.reason_label})` : ""}. [직접 작성] 하거나 [정책 근거 없음으로 진행] 할 수 있습니다.
            </AlertDescription>
            {data.status !== "empty" && (
              <Button size="sm" variant="outline" className="mt-2" onClick={() => fetchCards(data.excluded_docs)}>
                다시 시도
              </Button>
            )}
          </div>
        </Alert>
      ) : cards.length > 0 ? (
        <>
          <ul className="grid gap-3 md:grid-cols-2" aria-label="정책적 중요도 작성안 목록">
            {cards.map((c) => {
              const chosen = value?.card_ids?.includes(c.id) ?? false;
              return (
                <li key={c.id} className={cn("flex flex-col gap-2 rounded-lg border bg-card p-3", chosen && "border-primary")}>
                  <div className="flex items-center justify-between gap-2">
                    <Badge variant="secondary">{c.direction_label}</Badge>
                    <Label className="flex items-center gap-1 text-xs">
                      <Checkbox checked={merge.includes(c.id)} onChange={(e) => toggleMerge(c.id, e.target.checked)} />
                      합치기 선택<span className="sr-only"> — {c.direction_label}</span>
                    </Label>
                  </div>
                  <ul className="space-y-1 text-sm">
                    {c.sentences.map((s, i) => (
                      <li key={i}>
                        ○ <UntrustedText text={s.text} />
                      </li>
                    ))}
                  </ul>
                  <ul className="space-y-1" aria-label={`${c.direction_label} 근거`}>
                    {c.sources.map((s) => (
                      <SourceLine key={s.chunk_id} s={s} />
                    ))}
                  </ul>
                  <Button size="sm" className="mt-auto self-end" onClick={() => onChoose(choiceFromCard(c))} disabled={busy} aria-label={`이 안으로 — ${c.direction_label}`}>
                    {chosen ? "고른 안" : "이 안으로"}
                  </Button>
                </li>
              );
            })}
          </ul>
          <div className="flex flex-wrap items-center justify-end gap-2 text-xs text-muted-foreground">
            <span>작성안 {cards.length}개{data && data.dropped > 0 ? ` · 검사에서 버린 문장 ${data.dropped}` : ""}</span>
            <Button size="sm" variant="secondary" onClick={doMerge} disabled={merge.length !== 2 || busy}>
              두 안 합치기
            </Button>
          </div>
        </>
      ) : null}
    </section>
  );
}
