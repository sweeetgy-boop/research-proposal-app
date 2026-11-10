/** ① '핵심 문제' 카드 (ADR 0065, 계약 5절) — 네 칸을 AI 가 한 번 정리한 4줄(기능 문장·원인·모순·분류).
 *  줄마다 '근거 있음'/'추정'(제안문에 있는 내용인지 AI 가 채운 것인지)·'확인 필요', 줄마다 [고치기] → 그 줄만 고쳐 [적용].
 *  "전문가 분석 펼치기"는 기본 접힘(문제 성격·신호는 보이지 않는다). 카드 글은 모델 출력·제안자 수정(비신뢰) → UntrustedText. 열거값은 화면에 내보내지 않는다. */
import * as React from "react";
import { PencilLine } from "lucide-react";
import type { CardBasis, CardLines, ClassCode, ProblemCard as Card } from "@/api/types-problem-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/eyebrow";
import { UntrustedText } from "@/components/UntrustedText";
import {
  CARD_BADGES,
  CARD_EMPTY,
  CARD_EXPERT_LABELS,
  CARD_EXPERT_SUMMARY,
  CARD_FACET_LABELS,
  CARD_INPUT_CHANGED,
  CARD_INTRO,
  CARD_LINE_LABELS,
  CARD_PENDING,
  CARD_TITLE,
  principleLabel,
} from "@/lib/labels";
import { LineEditor } from "./ProblemCardEditors";
import { CARD_LINE_KEYS, lineByUser, type CardChange, type CardLineKey } from "./ProblemCardModel";

/** 진단 중 — 카드 자리에 작은 한 줄. 화면을 막지 않는다 */
export function ProblemCardPending() {
  return (
    <p role="status" className="text-sm text-muted-foreground" data-testid="problem-card-pending">
      {CARD_PENDING}
    </p>
  );
}

function Empty() {
  return <span className="text-muted-foreground">{CARD_EMPTY}</span>;
}

function BasisBadge({ basis }: { basis: CardBasis }) {
  return (
    <Badge variant={basis === "근거 있음" ? "success" : "warning"} data-testid="card-basis">
      {basis === "근거 있음" ? CARD_BADGES.stated : CARD_BADGES.guessed}
    </Badge>
  );
}

function CodeChips({ codes }: { codes: ClassCode[] }) {
  if (!codes.length) return <Empty />;
  return (
    <ul className="flex flex-wrap gap-x-3 gap-y-1">
      {codes.map((c) => (
        <li key={c.code} className="inline-flex flex-wrap items-center gap-1" data-testid="card-code">
          <UntrustedText text={c.label ? `${c.code} ${c.label}` : c.code} />
          {c.verified === "unverified" && (
            <Badge variant="secondary" data-testid="card-code-unverified">
              {CARD_BADGES.unverified}
            </Badge>
          )}
        </li>
      ))}
    </ul>
  );
}

/** 그 줄의 배지 재료 — 제안자가 고친 줄은 '직접 고침', 아니면 근거 수준. 분류는 성격상 AI 가 채운 것이라 '추정' */
function lineMeta(card: Card, key: CardLineKey): { basis: CardBasis | null; needsCheck: boolean } {
  if (key === "function") return { basis: card.function_ko.value ? card.function_ko.basis : null, needsCheck: card.function_ko.needs_check };
  if (key === "cause") {
    const c = card.causes[0];
    return { basis: c?.value ? c.basis : null, needsCheck: !!c?.needs_check };
  }
  if (key === "contradiction") {
    const filled = !!(card.contradiction.improve || card.contradiction.worsen);
    return { basis: filled ? card.contradiction.basis : null, needsCheck: false };
  }
  const ai = [...card.ipc, ...card.science_class].some((c) => c.origin === "ai");
  return { basis: ai ? "추정" : null, needsCheck: false };
}

function lineText(card: Card, lines: CardLines, key: Exclude<CardLineKey, "codes">): string {
  if (key === "function") return lines.function || card.function_ko.value;
  if (key === "cause") return lines.cause || (card.causes[0]?.value ?? "");
  const { improve, worsen } = card.contradiction;
  return lines.contradiction || (improve || worsen ? `${improve} ↔ ${worsen}` : "");
}

function ExpertItem({ title, children, testId }: { title: string; children: React.ReactNode; testId: string }) {
  return (
    <div data-testid={testId}>
      <h3 className="text-sm font-medium">{title}</h3>
      <div className="mt-1 text-sm">{children}</div>
    </div>
  );
}

/** 문제 성격(nature)·켜진 신호(signals)는 1차에 기록만 한다 — 카드에 들고 다니되 화면 어디에도 그리지 않는다 (2026-11-10 소유자 결정) */
function Expert({ card }: { card: Card }) {
  const facets = Object.keys(CARD_FACET_LABELS) as (keyof typeof CARD_FACET_LABELS)[];
  return (
    <details className="rounded-md border bg-background p-3" data-testid="problem-card-expert">
      <summary className="cursor-pointer text-sm font-semibold">{CARD_EXPERT_SUMMARY}</summary>
      <div className="mt-3 space-y-4">
        <ExpertItem title={CARD_EXPERT_LABELS.facets} testId="card-facets">
          <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-[7rem_1fr]">
            {facets.map((f) => (
              <React.Fragment key={f}>
                <dt className="text-muted-foreground">{CARD_FACET_LABELS[f]}</dt>
                <dd>{card.facets[f].value ? <UntrustedText text={card.facets[f].value} /> : <Empty />}</dd>
              </React.Fragment>
            ))}
          </dl>
        </ExpertItem>
        <ExpertItem title={CARD_EXPERT_LABELS.ladder} testId="card-ladder">
          {card.ladder.length ? (
            <ol className="space-y-1">
              {card.ladder.map((s) => (
                <li key={s.level}>
                  <span className="text-muted-foreground">{s.level}: </span>
                  {s.text ? <UntrustedText text={s.text} /> : <Empty />}
                </li>
              ))}
            </ol>
          ) : (
            <Empty />
          )}
        </ExpertItem>
        <ExpertItem title={CARD_EXPERT_LABELS.functionEn} testId="card-function-en">
          {card.function_en.value ? <span lang="en"><UntrustedText text={card.function_en.value} /></span> : <Empty />}
        </ExpertItem>
        <ExpertItem title={CARD_EXPERT_LABELS.causes} testId="card-causes">
          {card.causes.some((c) => c.value) ? (
            <ol className="space-y-1">
              {card.causes.map((c, i) => (
                <li key={i}>
                  <span className="text-muted-foreground">{i + 1}단계: </span>
                  {c.value ? <UntrustedText text={c.value} /> : <Empty />}
                </li>
              ))}
            </ol>
          ) : (
            <Empty />
          )}
        </ExpertItem>
        <ExpertItem title={CARD_EXPERT_LABELS.principles} testId="card-principles">
          {card.contradiction.principles.length ? (
            <ul className="flex flex-wrap gap-1.5">
              {card.contradiction.principles.map((p) => (
                <li key={p.number}>
                  <Badge variant="outline" className="whitespace-normal">
                    {principleLabel(p)}
                  </Badge>
                </li>
              ))}
            </ul>
          ) : (
            <Empty />
          )}
        </ExpertItem>
      </div>
    </details>
  );
}

export interface ProblemCardProps {
  card: Card;
  lines: CardLines;
  /** 네 칸이 카드를 만든 때와 달라졌다 — 다시 정리하는 동안은 고치기를 막는다 */
  changed?: boolean;
  /** 그때 보일 한 줄 (기본: 다시 정리하는 중) */
  changedNote?: string;
  /** 한 줄 [적용] — 서버가 돌려준 카드로 갈아 끼우는 일은 부르는 쪽. 실패하면 던진다(편집을 연 채 안내) */
  onEdit: (change: CardChange) => Promise<void>;
}

export function ProblemCard({ card, lines, changed = false, changedNote = CARD_INPUT_CHANGED, onEdit }: ProblemCardProps) {
  const [editing, setEditing] = React.useState<CardLineKey | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [failed, setFailed] = React.useState(false);

  const open = (key: CardLineKey) => {
    setFailed(false);
    setEditing(key);
  };
  const apply = async (change: CardChange | null) => {
    if (!change) return setEditing(null);
    setBusy(true);
    setFailed(false);
    try {
      await onEdit(change);
      setEditing(null);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-labelledby="problem-card-heading" className="space-y-3 rounded-lg border bg-card p-4" data-testid="problem-card">
      <div>
        <Eyebrow className="mb-1">Core problem</Eyebrow>
        <h2 id="problem-card-heading" className="text-base font-semibold">
          {CARD_TITLE}
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">{CARD_INTRO}</p>
      </div>
      {changed && (
        <p role="status" className="rounded-md border border-warning/30 bg-apricot p-2 text-sm text-apricot-foreground" data-testid="problem-card-changed">
          {changedNote}
        </p>
      )}
      <ul className="divide-y">
        {CARD_LINE_KEYS.map((key) => {
          const label = CARD_LINE_LABELS[key];
          const meta = lineMeta(card, key);
          const byUser = lineByUser(card, key);
          const text = key === "codes" ? "" : lineText(card, lines, key);
          return (
            <li key={key} className="py-3 first:pt-0 last:pb-0" data-testid={`card-line-${key}`}>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-sm font-semibold">{label}</span>
                {byUser ? (
                  <Badge variant="outline" data-testid="card-by-user">
                    {CARD_BADGES.user}
                  </Badge>
                ) : (
                  meta.basis && <BasisBadge basis={meta.basis} />
                )}
                {meta.needsCheck && (
                  <Badge variant="destructive" data-testid="card-needs-check">
                    {CARD_BADGES.needsCheck}
                  </Badge>
                )}
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="ml-auto"
                  onClick={() => open(key)}
                  disabled={changed || busy || editing === key}
                  aria-label={`${label} 고치기`}
                >
                  <PencilLine aria-hidden="true" />
                  고치기
                </Button>
              </div>
              {editing === key ? (
                <LineEditor line={key} card={card} busy={busy} failed={failed} onApply={(c) => void apply(c)} onCancel={() => setEditing(null)} />
              ) : (
                <div className="mt-1 text-sm" data-testid="card-line-text">
                  {key === "codes" ? <CodeChips codes={[...card.ipc, ...card.science_class]} /> : text ? <UntrustedText text={text} /> : <Empty />}
                </div>
              )}
            </li>
          );
        })}
      </ul>
      <Expert card={card} />
    </section>
  );
}
