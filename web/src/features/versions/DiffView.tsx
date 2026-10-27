import { diffChars } from "diff";
import type { DiffOut, DiffRow } from "@/api/types";
import { sectionTitle } from "@/lib/sections";
import { Badge } from "@/components/ui/badge";

/** 글자 단위 diff. 삭제·추가 문장을 같은 sentence_id(= 같은 자리)로 짝지어 비교한다. */
export function pairRows(removed: DiffRow[], added: DiffRow[]): { before: DiffRow | null; after: DiffRow | null }[] {
  const out: { before: DiffRow | null; after: DiffRow | null }[] = [];
  const usedAdded = new Set<number>();
  removed.forEach((r) => {
    const j = added.findIndex((a, k) => !usedAdded.has(k) && a.sentence_id === r.sentence_id);
    if (j >= 0 && added[j]) {
      usedAdded.add(j);
      out.push({ before: r, after: added[j]! });
    } else out.push({ before: r, after: null });
  });
  added.forEach((a, k) => {
    if (!usedAdded.has(k)) out.push({ before: null, after: a });
  });
  return out;
}

export function CharDiff({ before, after }: { before: string; after: string }) {
  const parts = diffChars(before, after);
  return (
    <p className="whitespace-pre-wrap text-sm leading-relaxed">
      {parts.map((p, i) =>
        p.added ? (
          <ins key={i} className="diff-ins">
            {p.value}
          </ins>
        ) : p.removed ? (
          <del key={i} className="diff-del">
            {p.value}
          </del>
        ) : (
          <span key={i}>{p.value}</span>
        ),
      )}
    </p>
  );
}

export function DiffView({ diff }: { diff: DiffOut }) {
  if (diff.sections.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        v{diff.from} 와 v{diff.to} 의 본문이 같습니다.
      </p>
    );
  }
  return (
    <div className="space-y-5">
      <p className="text-sm text-muted-foreground">
        v{diff.from} → v{diff.to}: 바뀐 섹션 {diff.sections.length}개.{" "}
        <ins className="diff-ins">추가</ins> · <del className="diff-del">삭제</del>
      </p>
      {diff.sections.map((s) => (
        <section key={s.section} aria-labelledby={`diff-${s.section}`} className="rounded-lg border p-3">
          <h3 id={`diff-${s.section}`} className="mb-2 flex flex-wrap items-center gap-2 text-base font-semibold">
            {sectionTitle(s.section)}
            <span className="text-xs font-normal text-muted-foreground">
              문장 {s.sentences[0]} → {s.sentences[1]}
            </span>
            {s.choices_changed && <Badge variant="info">선택값 변경</Badge>}
            {s.moved.length > 0 && <Badge variant="secondary">이동 {s.moved.length}</Badge>}
          </h3>
          <ul className="space-y-2">
            {pairRows(s.removed, s.added).map((p, i) => (
              <li key={i} className="rounded-md bg-muted/40 p-2">
                {p.before && p.after ? (
                  <CharDiff before={p.before.text} after={p.after.text} />
                ) : p.before ? (
                  <p className="text-sm">
                    <del className="diff-del whitespace-pre-wrap">{p.before.text}</del>
                  </p>
                ) : (
                  <p className="text-sm">
                    <ins className="diff-ins whitespace-pre-wrap">{p.after?.text}</ins>
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
