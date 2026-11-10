/** '핵심 문제' 카드의 줄 편집기 — 한 줄만 고친다. [적용] 때만 서버(diagnose/edit)로 간다. 빈 값으로 비워 둘 수 있다. */
import * as React from "react";
import { X } from "lucide-react";
import type { ClassCode, ProblemCard } from "@/api/types-problem-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { CARD_BADGES, CARD_CODE_KIND_LABELS, CARD_EDIT_FAILED, CARD_LINE_LABELS } from "@/lib/labels";
import {
  CARD_CODE_MAX,
  CARD_TEXT_MAX,
  CODE_LIMITS,
  changeCause,
  changeCodes,
  changeContradiction,
  changeFunction,
  newCode,
  type CardChange,
  type CardLineKey,
  type CodeKind,
} from "./ProblemCardModel";

export interface LineEditorProps {
  line: CardLineKey;
  card: ProblemCard;
  busy: boolean;
  failed: boolean;
  /** 바뀐 것이 없으면 null — 서버를 부르지 않고 닫는다 */
  onApply: (change: CardChange | null) => void;
  onCancel: () => void;
}

function Actions({ busy, failed, onCancel }: { busy: boolean; failed: boolean; onCancel: () => void }) {
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap gap-2">
        <Button type="submit" size="sm" disabled={busy}>
          {busy ? "적용 중…" : "적용"}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel} disabled={busy}>
          취소
        </Button>
      </div>
      <p className="min-h-5 text-sm text-destructive" aria-live="polite" data-testid="card-edit-error">
        {failed ? CARD_EDIT_FAILED : ""}
      </p>
    </div>
  );
}

function TextField({ id, label, value, onChange, autoFocus }: { id: string; label: string; value: string; onChange: (v: string) => void; autoFocus?: boolean }) {
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} value={value} maxLength={CARD_TEXT_MAX} onChange={(e) => onChange(e.target.value)} autoFocus={autoFocus} />
    </div>
  );
}

function CodeGroup({
  kind,
  codes,
  onChange,
}: {
  kind: CodeKind;
  codes: ClassCode[];
  onChange: (next: ClassCode[]) => void;
}) {
  const [draft, setDraft] = React.useState("");
  const label = CARD_CODE_KIND_LABELS[kind];
  const full = codes.length >= CODE_LIMITS[kind];
  const add = () => {
    const code = newCode(draft);
    if (!code || full) return;
    if (!codes.some((c) => c.code === code.code)) onChange([...codes, code]);
    setDraft("");
  };
  return (
    <div className="space-y-1.5" data-testid={`card-codes-${kind}`}>
      <p className="text-sm font-medium">
        {label} <span className="font-normal text-muted-foreground">· 최대 {CODE_LIMITS[kind]}개</span>
      </p>
      {codes.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {codes.map((c) => (
            <li key={c.code} className="inline-flex items-center gap-1 rounded-md border bg-card py-0.5 pl-2 pr-0.5 text-sm">
              <span>{c.code}</span>
              {c.verified === "unverified" && <Badge variant="secondary">{CARD_BADGES.unverified}</Badge>}
              <button
                type="button"
                className="inline-flex size-7 items-center justify-center rounded-md hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
                aria-label={`${c.code} 삭제`}
                onClick={() => onChange(codes.filter((x) => x.code !== c.code))}
              >
                <X className="size-4" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-40 flex-1 space-y-1">
          <Label htmlFor={`card-code-${kind}`}>{label} 코드 추가</Label>
          <Input
            id={`card-code-${kind}`}
            value={draft}
            maxLength={CARD_CODE_MAX}
            disabled={full}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
          />
        </div>
        <Button type="button" size="sm" variant="outline" onClick={add} disabled={full || !draft.trim()}>
          추가
        </Button>
      </div>
    </div>
  );
}

/** 줄 하나의 편집 폼 — 기능 문장·원인은 한 칸, 모순은 두 칸, 분류는 코드 추가·삭제 */
export function LineEditor({ line, card, busy, failed, onApply, onCancel }: LineEditorProps) {
  const [text, setText] = React.useState(line === "function" ? card.function_ko.value : (card.causes[0]?.value ?? ""));
  const [improve, setImprove] = React.useState(card.contradiction.improve);
  const [worsen, setWorsen] = React.useState(card.contradiction.worsen);
  const [ipc, setIpc] = React.useState(card.ipc);
  const [science, setScience] = React.useState(card.science_class);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (line === "function") onApply(changeFunction(card, text));
    else if (line === "cause") onApply(changeCause(card, text));
    else if (line === "contradiction") onApply(changeContradiction(card, improve, worsen));
    else onApply(changeCodes(card, ipc, science));
  };

  return (
    <form onSubmit={submit} noValidate className="mt-2 space-y-3 rounded-md border bg-background p-3" aria-label={`${CARD_LINE_LABELS[line]} 고치기`}>
      {(line === "function" || line === "cause") && (
        <TextField id={`card-edit-${line}`} label={CARD_LINE_LABELS[line]} value={text} onChange={setText} autoFocus />
      )}
      {line === "contradiction" && (
        <div className="grid gap-3 sm:grid-cols-2">
          <TextField id="card-edit-improve" label="좋게 하려는 것" value={improve} onChange={setImprove} autoFocus />
          <TextField id="card-edit-worsen" label="그 때문에 나빠지는 것" value={worsen} onChange={setWorsen} />
        </div>
      )}
      {line === "codes" && (
        <div className="space-y-4">
          <CodeGroup kind="ipc" codes={ipc} onChange={setIpc} />
          <CodeGroup kind="science_class" codes={science} onChange={setScience} />
        </div>
      )}
      <Actions busy={busy} failed={failed} onCancel={onCancel} />
    </form>
  );
}
