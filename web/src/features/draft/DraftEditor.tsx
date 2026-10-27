import * as React from "react";
import { MessageSquareText, Plus } from "lucide-react";
import type { Annotation, ReviewComment, VersionSection, VersionSentence } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { OriginBadge } from "@/components/OriginBadge";
import { UntrustedText } from "@/components/UntrustedText";
import { VirtualList } from "@/components/VirtualList";
import { sectionTitle, CHOICE_SECTIONS } from "@/lib/sections";
import { cn } from "@/lib/utils";
import type { Action, EditState, SentenceState } from "./editModel";

type Row = { kind: "header"; key: string; section: VersionSection } | { kind: "sentence"; key: string; section: VersionSection; sentence: VersionSentence };

const ACTIONS: { id: Action; label: string }[] = [
  { id: "keep", label: "원문 유지" },
  { id: "use_revision", label: "수정안 사용" },
  { id: "manual", label: "직접 수정" },
  { id: "delete", label: "삭제" },
];

export interface DraftEditorProps {
  sections: VersionSection[];
  annotations: Annotation[];
  revisions: Map<string, ReviewComment[]>;
  state: EditState;
  onChange: (next: EditState) => void;
  disabled?: boolean;
}

function AnnotationList({ items, state, onChange, disabled }: { items: Annotation[]; state: EditState; onChange: (s: EditState) => void; disabled?: boolean }) {
  if (items.length === 0) return null;
  const toggle = (id: string, done: boolean) =>
    onChange({ ...state, doneAnnotations: done ? [...new Set([...state.doneAnnotations, id])] : state.doneAnnotations.filter((x) => x !== id) });
  return (
    <ul className="mt-1 space-y-1">
      {items.map((a) => {
        const done = a.status === "done" || state.doneAnnotations.includes(a.id);
        return (
          <li key={a.id} className={cn("flex items-start gap-2 rounded-md border border-dashed p-2 text-sm", done && "opacity-60")}>
            <MessageSquareText className="mt-0.5 size-4 shrink-0 text-origin-argon" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
                <span className="font-mono">{a.id}</span>
                <Badge variant="outline">{a.kind === "section" ? "섹션 의견" : a.kind === "discarded" ? "폐기된 수정안" : "의견"}</Badge>
                {a.reason && <span>사유: {a.reason}</span>}
              </div>
              <UntrustedText as="p" text={a.text} />
            </div>
            <Label className="flex items-center gap-1.5 whitespace-nowrap text-xs">
              <Checkbox checked={done} disabled={disabled || a.status === "done"} onChange={(e) => toggle(a.id, e.target.checked)} />
              처리됨
            </Label>
          </li>
        );
      })}
    </ul>
  );
}

function SentenceEditor({
  sentence,
  st,
  revisions,
  onSentence,
  disabled,
  locked,
  sectionLabel,
}: {
  sentence: VersionSentence;
  st: SentenceState;
  sectionLabel: string;
  revisions: ReviewComment[];
  onSentence: (patch: Partial<SentenceState>) => void;
  disabled?: boolean;
  locked: boolean; // 섹션 통문 편집 중
}) {
  const sid = sentence.sentence_id;
  const [showInsert, setShowInsert] = React.useState(!!st.inserted);
  const groupId = `act-${sid}`;
  const idx = Number(sid.split(":")[2] ?? 0) + 1;
  return (
    <div className={cn("space-y-2 py-2", st.action === "delete" && "opacity-70")}>
      <div className="flex gap-2">
        <span className="w-6 shrink-0 pt-0.5 text-right text-xs tabular-nums text-muted-foreground" aria-hidden="true">
          {idx}
        </span>
        <div className="min-w-0 flex-1">
          <UntrustedText as="p" text={sentence.text} className={cn(st.action === "delete" && "line-through")} />
          <div className="mt-1 flex flex-wrap items-center gap-1">
            <OriginBadge origin={sentence.origin} />
            {sentence.evidence.length > 0 && <Badge variant="outline">근거 {sentence.evidence.length}</Badge>}
            {revisions.length > 0 && <Badge variant="info">수정안 {revisions.length}</Badge>}
          </div>
        </div>
      </div>
      {!locked && (
        <fieldset className="ml-8 space-y-2" disabled={disabled}>
          <legend className="sr-only">{sectionLabel} 문장 {idx} 처리</legend>
          <div role="radiogroup" aria-label={`${sectionLabel} 문장 ${idx} 처리`} className="flex flex-wrap gap-1">
            {ACTIONS.filter((a) => a.id !== "use_revision" || revisions.length > 0).map((a) => {
              const on = st.action === a.id;
              return (
                <label
                  key={a.id}
                  className={cn(
                    "inline-flex min-h-9 cursor-pointer items-center gap-1.5 rounded-md border px-2.5 text-sm has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring",
                    on ? "border-primary bg-primary text-primary-foreground" : "hover:bg-accent",
                  )}
                >
                  <input type="radio" name={groupId} value={a.id} checked={on} onChange={() => onSentence({ action: a.id })} className="sr-only" />
                  {a.label}
                </label>
              );
            })}
          </div>
          {st.action === "use_revision" && (
            <div className="space-y-1">
              {revisions.map((c) => {
                const chosen = (st.commentId ?? revisions[0]?.id) === c.id;
                return (
                  <label key={c.id} className={cn("flex cursor-pointer items-start gap-2 rounded-md border p-2 text-sm", chosen && "border-primary")}>
                    <input type="radio" name={`rev-${sid}`} checked={chosen} onChange={() => onSentence({ commentId: c.id })} className="mt-1" />
                    <span className="min-w-0 flex-1">
                      <span className="block text-xs text-muted-foreground">
                        {c.id} · {c.issue_type} — <UntrustedText text={c.comment} />
                      </span>
                      <UntrustedText as="span" text={c.revised_text} className="diff-ins" />
                    </span>
                  </label>
                );
              })}
            </div>
          )}
          {st.action === "manual" && (
            <div className="space-y-1">
              <Label htmlFor={`man-${sid}`} className="sr-only">
                문장 {idx} 직접 수정
              </Label>
              <Textarea id={`man-${sid}`} rows={2} value={st.text ?? sentence.text} onChange={(e) => onSentence({ text: e.target.value })} maxLength={4000} />
              <p className="text-xs text-muted-foreground">원래 근거를 이어받습니다 (출처: 제안자 수정).</p>
            </div>
          )}
          {showInsert ? (
            <div className="space-y-1">
              <Label htmlFor={`ins-${sid}`} className="text-xs">
                이 문장 뒤에 추가 (근거 없음, 제안자 입력)
              </Label>
              <Textarea id={`ins-${sid}`} rows={2} value={st.inserted ?? ""} onChange={(e) => onSentence({ inserted: e.target.value })} maxLength={4000} />
            </div>
          ) : (
            <Button variant="ghost" size="sm" onClick={() => setShowInsert(true)}>
              <Plus aria-hidden="true" />
              뒤에 문장 추가
            </Button>
          )}
        </fieldset>
      )}
    </div>
  );
}

export function DraftEditor({ sections, annotations, revisions, state, onChange, disabled }: DraftEditorProps) {
  const rows: Row[] = [];
  for (const sec of sections) {
    rows.push({ kind: "header", key: `h:${sec.key}`, section: sec });
    for (const s of sec.sentences) rows.push({ kind: "sentence", key: s.sentence_id, section: sec, sentence: s });
  }
  const setSentence = (sid: string, patch: Partial<SentenceState>) =>
    onChange({ ...state, sentences: { ...state.sentences, [sid]: { ...(state.sentences[sid] ?? { action: "keep" }), ...patch } } });
  const toggleSectionText = (sec: VersionSection, on: boolean) => {
    const next = { ...state.sectionText };
    if (on) next[sec.key] = sec.sentences.map((s) => s.text).join("\n");
    else delete next[sec.key];
    onChange({ ...state, sectionText: next });
  };

  const renderRow = (row: Row) => {
    if (row.kind === "header") {
      const sec = row.section;
      const whole = state.sectionText[sec.key] !== undefined;
      const secAnn = annotations.filter((a) => a.section === sec.key && a.sentence === null);
      return (
        <div className="mt-6 border-b pb-2 first:mt-0">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-base font-semibold">{sectionTitle(sec.key)}</h3>
            {!CHOICE_SECTIONS.has(sec.key) || sec.sentences.length > 0 ? (
              <Label className="flex items-center gap-1.5 text-sm">
                <Checkbox checked={whole} disabled={disabled} onChange={(e) => toggleSectionText(sec, e.target.checked)} />
                섹션 전체를 통문으로 편집
              </Label>
            ) : (
              <span className="text-sm text-muted-foreground">체크 칸 (최종 마무리에서 확정)</span>
            )}
          </div>
          {whole && (
            <div className="mt-2 space-y-1">
              <Label htmlFor={`sec-${sec.key}`} className="sr-only">
                {sectionTitle(sec.key)} 통문
              </Label>
              <Textarea
                id={`sec-${sec.key}`}
                rows={Math.max(4, sec.sentences.length + 1)}
                value={state.sectionText[sec.key] ?? ""}
                onChange={(e) => onChange({ ...state, sectionText: { ...state.sectionText, [sec.key]: e.target.value } })}
                disabled={disabled}
                maxLength={20000}
              />
              <p className="text-xs text-muted-foreground">줄마다 한 문장. 같은 문장은 근거를 이어받고 새 문장은 근거 없음으로 저장됩니다.</p>
            </div>
          )}
          <AnnotationList items={secAnn} state={state} onChange={onChange} disabled={disabled} />
        </div>
      );
    }
    const sid = row.sentence.sentence_id;
    const st = state.sentences[sid] ?? { action: "keep" as const };
    const ann = annotations.filter((a) => a.sentence_id === sid);
    return (
      <div>
        <SentenceEditor
          sentence={row.sentence}
          st={st}
          revisions={revisions.get(sid) ?? []}
          onSentence={(p) => setSentence(sid, p)}
          disabled={disabled}
          locked={state.sectionText[row.section.key] !== undefined}
          sectionLabel={sectionTitle(row.section.key)}
        />
        {ann.length > 0 && (
          <div className="ml-8 pb-2">
            <AnnotationList items={ann} state={state} onChange={onChange} disabled={disabled} />
          </div>
        )}
      </div>
    );
  };

  if (rows.length > 80) {
    return <VirtualList items={rows} getKey={(r) => r.key} estimate={120} renderRow={renderRow} as="div" ariaLabel="초안 문장 편집" />;
  }
  return (
    <div>
      {rows.map((r) => (
        <React.Fragment key={r.key}>{renderRow(r)}</React.Fragment>
      ))}
    </div>
  );
}
