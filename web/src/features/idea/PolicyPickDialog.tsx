import * as React from "react";
import { BookMarked, ExternalLink, RefreshCw } from "lucide-react";
import { fetchPolicySuggestions, formatPolicyQuote, type PolicyProbe, type PolicySuggestion } from "@/api/policySuggestions";
import type { ProposalRequest } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { UntrustedText } from "@/components/UntrustedText";
import { AiCancelledNote, AiWaiting } from "@/components/AiWaiting";
import { DocRef } from "@/components/DocRef";
import { useAiCall } from "@/lib/useAiCall";
import { SLOT_MAX } from "@/lib/validation";
import { cn } from "@/lib/utils";

export const POLICY_UNAVAILABLE = "정책 근거 추천은 정책 자료 적재 뒤 열립니다.";
export const POLICY_LATER_NOTE = "정책적 중요도가 빈칸으로 생성될 수 있습니다. ③ 보강 질문·④ 직접 수정에서 다시 넣을 수 있습니다.";

const keyOf = (s: PolicySuggestion) => `${s.doc_id}\u0000${s.quote}`;

/** 추천 한 건의 출처 줄 — 문서명(근거 패널)·연도·위치·[원문] 링크. 화면은 내부 문서 번호를 보이지 않는다. */
export function PolicyQuoteMeta({ s }: { s: PolicySuggestion }) {
  return (
    <div className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
      <DocRef docRef={{ doc_id: s.doc_id, title: s.document, source: s.source, source_label: s.source_label, url: s.url, summary: s.quote }} compact />
      {s.year ? <span>· {s.year}</span> : null}
      {s.page ? (
        <span>
          · <UntrustedText text={String(s.page)} />
        </span>
      ) : null}
      {s.url && (
        <a href={s.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-0.5 underline">
          · 원문 <ExternalLink className="size-3" aria-hidden="true" />
          <span className="sr-only">(새 창, {s.document})</span>
        </a>
      )}
    </div>
  );
}

/** ① 정책 근거 추천 팝업 (ADR 0052) — 열리면 바로 추천을 받는다(시간 제한 없음, 경과 초와 [취소]).
 *  관련도 1순위는 미리 체크해 두고 "기본 추천" 배지 — 미리 골라 둔 것일 뿐 자동 저장이 아니다.
 *  다른 추천 추가 체크 + 직접 입력 → [적용] 을 눌러야만 정책 근거 칸에 들어간다(ADR 0040 "고른 것만 덧붙임" 유지).
 *  [다시 받기] 는 이미 본 문서를 빼고 받으며, 앞서 받은 추천과 체크는 그대로 둔다. 정책 자료만 —
 *  사전정보공표 연구용역(사내 발주)·행정 공시·사업 현황은 나오지 않고, 공용 계정은 사내 비공개 자료가 빠진다(서버). */
export function PolicyPickDialog({
  open,
  request,
  gate = false,
  onApply,
  onLater,
  onClose,
}: {
  open: boolean;
  request: ProposalRequest;
  /** [다음: 유사과제 확인] 에서 열었다 — 두 버튼 모두 고른 뒤 ② 로 넘어간다 */
  gate?: boolean;
  /** 고른 추천 문구(formatPolicyQuote) + 직접 입력 — 칸에 덧붙이기는 부른 쪽(mergePolicyBasis) */
  onApply: (additions: string[]) => void;
  onLater: () => void;
  /** Esc·닫기 — 아무것도 바꾸지 않는다 */
  onClose: () => void;
}) {
  const call = useAiCall((exclude: string[], signal) => fetchPolicySuggestions(request, signal, exclude));
  const [items, setItems] = React.useState<PolicySuggestion[]>([]);
  const [picked, setPicked] = React.useState<Set<string>>(new Set());
  const [defaultKey, setDefaultKey] = React.useState<string | null>(null);
  const [direct, setDirect] = React.useState("");
  const [probe, setProbe] = React.useState<PolicyProbe | null>(null);
  const [fresh, setFresh] = React.useState<number | null>(null);
  const ready = Boolean(request.current_state && request.root_cause && request.limitation && request.goal);
  const runCall = call.run;
  const cancel = call.cancel;

  const load = React.useCallback(
    async (exclude: string[], first: boolean) => {
      const out = await runCall(exclude);
      if (!out) return; // 취소·호출 오류(call.error) — 앞 상태 그대로
      setProbe(out);
      if (out.state !== "ok") return;
      setItems((prev) => {
        const known = new Set(prev.map(keyOf));
        return [...prev, ...out.items.filter((s) => !known.has(keyOf(s)))];
      });
      setFresh(first ? null : out.items.length);
      const top = out.items[0];
      if (first && top) {
        setDefaultKey(keyOf(top));
        setPicked(new Set([keyOf(top)]));
      }
    },
    [runCall],
  );

  // 열 때마다 새로: 상태를 비우고 바로 추천을 받는다. 닫으면 기다리던 호출을 끊는다.
  React.useEffect(() => {
    if (!open) {
      cancel();
      return;
    }
    setItems([]);
    setPicked(new Set());
    setDefaultKey(null);
    setDirect("");
    setProbe(null);
    setFresh(null);
    if (ready) void load([], true);
    // 열릴 때 한 번만 — 입력은 그 시점 것
  }, [open]);

  const seen = [...new Set(items.map((s) => s.doc_id))];
  const unavailable = probe?.state === "unavailable";
  const hasList = items.length > 0;
  const chosen = items.filter((s) => picked.has(keyOf(s)));
  const canApply = chosen.length > 0 || direct.trim().length > 0;
  const toggle = (s: PolicySuggestion, on: boolean) =>
    setPicked((p) => {
      const next = new Set(p);
      if (on) next.add(keyOf(s));
      else next.delete(keyOf(s));
      return next;
    });
  const apply = () => onApply([...chosen.map(formatPolicyQuote), direct.trim()].filter(Boolean));

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="정책 근거 추천"
      description={
        gate
          ? "정책 근거 칸이 비어 있습니다. 정책적 중요도(2-가-(1))는 이 칸만 근거로 씁니다 — 고르거나 직접 적은 뒤 유사과제 확인으로 넘어갑니다."
          : "정책적 중요도(2-가-(1))는 정책 근거 칸만 근거로 씁니다. 고른 추천과 직접 입력이 칸 뒤에 덧붙습니다."
      }
      className="w-[min(96vw,48rem)]"
      footer={
        <>
          <Button variant="outline" onClick={onLater}>
            나중에 넣기
          </Button>
          {(hasList || direct.trim()) && (
            <Button onClick={apply} disabled={!canApply}>
              적용{chosen.length + (direct.trim() ? 1 : 0) > 0 ? ` (${chosen.length + (direct.trim() ? 1 : 0)}건)` : ""}
            </Button>
          )}
        </>
      }
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            <BookMarked className="size-4 shrink-0" aria-hidden="true" />
            국토부 계획·공사 경영목표·전략·감사 지적·정부 R&amp;D 공고에서 찾은 문구입니다(수집 자료, 비신뢰). [적용] 을 눌러야 칸에 들어갑니다.
          </p>
          {ready && !unavailable && (
            <Button variant="outline" size="sm" onClick={() => void load(seen, false)} disabled={call.pending}>
              <RefreshCw className={call.pending ? "animate-spin" : ""} aria-hidden="true" />
              다시 받기
            </Button>
          )}
        </div>

        {!ready && <p className="text-sm text-muted-foreground">필수 4칸(현황·원인·한계·목표)을 채우면 추천을 받을 수 있습니다. 아는 정책은 아래에 직접 적을 수 있습니다.</p>}
        <AiWaiting pending={call.pending} elapsed={call.elapsed} onCancel={call.cancel} what="정책 근거 추천" />
        <AiCancelledNote show={call.cancelled} />
        {call.pending && !hasList && <SkeletonBlock lines={3} />}
        <ProblemBanner error={call.error} onRetry={() => void load(seen, !hasList)} />
        {probe?.state === "error" && <ProblemBanner error={probe.error} onRetry={() => void load(seen, !hasList)} />}
        {unavailable && (
          <p className="text-sm text-muted-foreground" role="status">
            {POLICY_UNAVAILABLE} 아는 정책·계획명을 직접 적거나 나중에 넣을 수 있습니다.
          </p>
        )}
        {probe?.state === "ok" && !hasList && (
          <p className="text-sm text-muted-foreground" role="status">
            해당 없음 — 아이디어와 관련된 정책 문구를 찾지 못했습니다. 아는 정책·계획명을 직접 적거나 나중에 넣을 수 있습니다.
          </p>
        )}
        {fresh !== null && (
          <p className="text-xs text-muted-foreground" role="status">
            {fresh > 0 ? `이미 본 문서를 빼고 ${fresh}건을 더 받았습니다 (아래에 붙음).` : "이미 본 문서 말고는 더 찾은 문구가 없습니다."}
          </p>
        )}

        {hasList && (
          <fieldset className="space-y-2">
            <legend className="mb-1 text-sm font-medium">추천 {items.length}건 — 넣을 것을 고르십시오</legend>
            <ul className="space-y-2" aria-label="정책 근거 추천 목록">
              {items.map((s, i) => {
                const k = keyOf(s);
                const on = picked.has(k);
                const id = `policy-pick-${i}`;
                return (
                  <li key={k} className={cn("flex items-start gap-3 rounded-md border bg-card p-3 text-sm", on && "border-primary")}>
                    <Checkbox id={id} checked={on} onChange={(e) => toggle(s, e.target.checked)} className="mt-0.5" />
                    <div className="min-w-0 flex-1 space-y-1">
                      <div className="flex flex-wrap items-start gap-2">
                        <label htmlFor={id} className="min-w-0 flex-1 cursor-pointer">
                          <blockquote className="border-l-2 pl-2">
                            <UntrustedText as="span" text={`“${s.quote}”`} />
                          </blockquote>
                        </label>
                        {k === defaultKey && <Badge variant="secondary">기본 추천</Badge>}
                      </div>
                      <PolicyQuoteMeta s={s} />
                    </div>
                  </li>
                );
              })}
            </ul>
          </fieldset>
        )}

        <div className="space-y-1.5">
          <Label htmlFor="policy-direct">직접 입력 (선택)</Label>
          <p id="policy-direct-hint" className="text-xs text-muted-foreground">
            아는 정책·계획명과 요지 — 고른 추천과 함께 정책 근거 칸에 들어갑니다.
          </p>
          <Textarea id="policy-direct" rows={3} maxLength={SLOT_MAX} value={direct} onChange={(e) => setDirect(e.target.value)} aria-describedby="policy-direct-hint" />
        </div>
        <p className="text-xs text-muted-foreground">
          {hasList ? "기본 추천은 미리 골라 둔 것일 뿐입니다 — [적용] 을 눌러야 칸에 들어갑니다. " : ""}[나중에 넣기] 를 고르면 칸은 비어 있고, ③ 보강 질문·④ 직접 수정에서 다시 넣을 수 있습니다.
        </p>
      </div>
    </Dialog>
  );
}
