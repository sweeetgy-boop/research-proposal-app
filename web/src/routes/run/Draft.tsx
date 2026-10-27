import * as React from "react";
import { Link } from "react-router";
import { AlertTriangle, BookOpen } from "lucide-react";
import { useRunContext } from "./useRunContext";
import { useDraft, useDraftReview, useOutline, useVersion } from "@/api/hooks";
import type { Citation, DraftSection, VersionSection } from "@/api/types";
import { Tabs, TabPanel } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { OriginBadge } from "@/components/OriginBadge";
import { UntrustedText } from "@/components/UntrustedText";
import { VirtualList } from "@/components/VirtualList";
import { EvidenceChips } from "@/features/draft/EvidenceChips";
import { ReviewPanel } from "@/features/draft/ReviewPanel";
import { sectionTitle, CHOICE_SECTIONS } from "@/lib/sections";

type Row =
  | { kind: "header"; key: string; section: DraftSection | VersionSection }
  | { kind: "sentence"; key: string; section: string; index: number; text: string; origin: string; evidence: string[]; source: string };

function toRows(sections: (DraftSection | VersionSection)[]): Row[] {
  const rows: Row[] = [];
  for (const sec of sections) {
    rows.push({ kind: "header", key: `h:${sec.key}`, section: sec });
    sec.sentences.forEach((s, i) =>
      rows.push({ kind: "sentence", key: `s:${sec.key}:${i}`, section: sec.key, index: i, text: s.text, origin: s.origin, evidence: s.evidence, source: s.source }),
    );
  }
  return rows;
}

function SectionHeader({ section }: { section: DraftSection | VersionSection }) {
  const choices = "choices" in section && section.choices && !Array.isArray(section.choices) ? section.choices : null;
  return (
    <div className="mt-6 border-b pb-1 first:mt-0">
      <h3 className="text-base font-semibold">{sectionTitle(section.key)}</h3>
      {choices && (
        <p className="mt-1 text-sm">
          <span className="text-muted-foreground">제안값: </span>
          {choices.proposed.length ? choices.proposed.map((c) => <Badge key={c.id} variant="secondary" className="mr-1 whitespace-normal text-left">{c.label}</Badge>) : "—"}
          {choices.confirmed && (
            <>
              <span className="ml-2 text-muted-foreground">확정: </span>
              {choices.confirmed.map((c) => <Badge key={c.id} variant="success" className="mr-1 whitespace-normal text-left">{c.label}</Badge>)}
            </>
          )}
        </p>
      )}
      {section.sentences.length === 0 && (
        <p className="mt-1 text-sm text-muted-foreground">
          {CHOICE_SECTIONS.has(section.key) ? "(본문 없이 체크 칸으로만 들어갑니다)" : "문장이 없습니다 — 근거·입력이 부족해 빈칸으로 둡니다. 직접 수정에서 채울 수 있습니다."}
        </p>
      )}
    </div>
  );
}

function SentenceLine({ row, citations, problem }: { row: Extract<Row, { kind: "sentence" }>; citations: Citation[]; problem?: string }) {
  return (
    <div className="flex gap-2 py-1.5">
      <span className="w-6 shrink-0 pt-0.5 text-right text-xs tabular-nums text-muted-foreground" aria-hidden="true">
        {row.index + 1}
      </span>
      <div className="min-w-0 flex-1">
        <UntrustedText as="p" text={row.text} />
        <div className="mt-1 flex flex-wrap items-center gap-1">
          <OriginBadge origin={row.origin} />
          {row.source === "proposer_input" && row.evidence.length === 0 && row.section !== "title" && <Badge variant="outline">근거 없음</Badge>}
          {problem && (
            <Badge variant="warning">
              <AlertTriangle className="mr-1 size-3" aria-hidden="true" />
              {problem}
            </Badge>
          )}
        </div>
        <EvidenceChips evidence={row.evidence} citations={citations} />
      </div>
    </div>
  );
}

export default function Draft() {
  const { run } = useRunContext();
  const id = run.run_id;
  const draft = useDraft(id);
  const review = useDraftReview(id);
  const outline = useOutline(id);
  const versions = draft.data?.versions ?? [];
  const [tab, setTab] = React.useState<string>("current");
  const selected = tab === "current" ? null : Number(tab);
  const version = useVersion(id, selected);

  if (draft.isPending) {
    return (
      <div className="space-y-4" aria-busy="true">
        <SkeletonBlock lines={2} />
        <SkeletonBlock lines={8} />
      </div>
    );
  }
  if (draft.error || !draft.data) return <ProblemBanner error={draft.error} onRetry={() => draft.refetch()} />;
  const d = draft.data;
  const sections: (DraftSection | VersionSection)[] = selected === null ? d.sections : (version.data?.sections ?? []);
  const rows = toRows(sections);
  const problemBySentence = new Map<string, string>();
  const sectionProblems = d.problems.filter((p) => p.sentence === null);
  for (const p of d.problems) if (p.sentence !== null) problemBySentence.set(`s:${p.section}:${p.sentence}`, p.message);

  const tabs = [{ id: "current", label: `현재 v${d.version}` }, ...versions.filter((v) => v !== d.version).map((v) => ({ id: String(v), label: `v${v}` }))];

  const renderRow = (row: Row) =>
    row.kind === "header" ? <SectionHeader section={row.section} /> : <SentenceLine row={row} citations={d.citations} problem={problemBySentence.get(row.key)} />;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="min-w-0 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">초안 본문</h2>
          <Link to={`/runs/${id}/edit`} className={buttonVariants({ variant: "outline", size: "sm" })}>
            직접 수정 →
          </Link>
        </div>
        <Tabs items={tabs} value={tab} onChange={setTab} label="초안 버전" />
        {tabs.map((t) => (
          <TabPanel key={t.id} id={t.id} active={t.id === tab}>
            {selected !== null && version.isPending ? (
              <SkeletonBlock lines={8} />
            ) : rows.length > 60 ? (
              <VirtualList items={rows} getKey={(r) => r.key} estimate={64} renderRow={renderRow} as="div" ariaLabel="초안 문장" />
            ) : (
              <div>
                {rows.map((r) => (
                  <React.Fragment key={r.key}>{renderRow(r)}</React.Fragment>
                ))}
              </div>
            )}
          </TabPanel>
        ))}
      </div>

      <aside className="min-w-0 space-y-6">
        <section aria-labelledby="problems-h" className="rounded-lg border p-3">
          <h2 id="problems-h" className="mb-2 flex items-center gap-2 text-base font-semibold">
            <AlertTriangle className="size-4" aria-hidden="true" />
            알림 {d.problems.length}건
          </h2>
          {d.problems.length === 0 ? (
            <p className="text-sm text-muted-foreground">규칙 검사 알림이 없습니다.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {d.problems.map((p, i) => (
                <li key={i} className="flex flex-wrap gap-1">
                  <Badge variant={p.severity === "error" ? "destructive" : "warning"}>{p.severity}</Badge>
                  <span className="text-muted-foreground">
                    {sectionTitle(p.section)}
                    {p.sentence !== null ? ` 문장 ${p.sentence + 1}` : ""}:
                  </span>
                  <UntrustedText text={p.message} />
                </li>
              ))}
            </ul>
          )}
          {sectionProblems.length === 0 && d.problems.length > 0 && <p className="sr-only">문장 단위 알림은 본문 옆 배지로도 표시됩니다.</p>}
        </section>

        <section aria-labelledby="cite-h" className="rounded-lg border p-3">
          <h2 id="cite-h" className="mb-2 flex items-center gap-2 text-base font-semibold">
            <BookOpen className="size-4" aria-hidden="true" />
            인용 문서 {d.citations.length}건
          </h2>
          {d.citations.length === 0 ? (
            <p className="text-sm text-muted-foreground">인용된 근거가 없습니다.</p>
          ) : (
            <ol className="space-y-1 text-sm">
              {d.citations.map((c) => (
                <li key={c.id}>
                  <UntrustedText text={c.title ?? c.doc_id} className="font-medium" />
                  <span className="ml-1 font-mono text-xs text-muted-foreground">{c.id}</span>
                </li>
              ))}
            </ol>
          )}
        </section>

        <div className="rounded-lg border p-3">
          {review.isPending ? (
            <SkeletonBlock lines={4} />
          ) : review.data ? (
            <ReviewPanel review={review.data} title="Argon 1차 검토" />
          ) : (
            <section>
              <h2 className="text-base font-semibold">Argon 1차 검토</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {d.review.skipped ? "검토 모델 키가 없어 1차 검토를 건너뛰었습니다. v1 로 바로 수정 단계로 갑니다." : "1차 검토 결과가 아직 없습니다."}
              </p>
            </section>
          )}
        </div>

        <details className="rounded-lg border p-3">
          <summary className="cursor-pointer text-base font-semibold">설계도 (섹션 구상)</summary>
          <div className="mt-2 text-sm">
            {outline.isPending ? (
              <SkeletonBlock lines={3} />
            ) : outline.data ? (
              <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded bg-muted/60 p-2 text-xs">{JSON.stringify(outline.data.outline, null, 2)}</pre>
            ) : (
              <p className="text-muted-foreground">설계도가 없습니다 (pipeline.outline 이 꺼져 있습니다).</p>
            )}
          </div>
        </details>
      </aside>
    </div>
  );
}
