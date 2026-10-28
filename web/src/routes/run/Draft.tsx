import * as React from "react";
import { Link, useSearchParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, BookOpen, RefreshCw } from "lucide-react";
import { useRunContext } from "./useRunContext";
import { keys, useDraft, useDraftReview, useOutline, useSubmitCheck, useVersion } from "@/api/hooks";
import type { Citation, DraftSection, FailedSection, FallbackSection, Problem_, SectionWriter, VersionSection } from "@/api/types";
import { SectionRewrite } from "@/features/rewrite/SectionRewrite";
import { useToast } from "@/components/ui/toast";
import { EvidencePanel } from "@/features/evidence/EvidencePanel";
import { FigureList } from "@/features/figures/FigureList";
import { Button } from "@/components/ui/button";
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
import { WriterBadges } from "@/features/draft/WriterBadges";
import { LiveBadge } from "@/features/live/LiveBadge";
import { LOCAL_EVIDENCE_MISMATCH, LOCAL_EVIDENCE_MISMATCH_LABEL } from "@/lib/writer";

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

function SectionHeader({
  section,
  failed,
  onRegenerate,
  fallback,
  local,
  writer,
}: {
  section: DraftSection | VersionSection;
  /** 빈 초안 금지(ADR 0027): 로컬 작성 실패 → 빈칸 + "이 섹션 다시 생성" (현재 버전에서만) */
  failed?: FailedSection;
  onRegenerate?: (key: string) => void;
  /** 대체 작성(ADR 0027): 로컬 2회 실패 뒤 외부 LLM 이 쓴 섹션 — 배지만 */
  fallback?: FallbackSection;
  /** [3] Argon 실패 뒤 로컬 모델이 쓴 섹션 — "로컬 작성" 배지 */
  local?: boolean;
  writer?: SectionWriter;
}) {
  const choices = "choices" in section && section.choices && !Array.isArray(section.choices) ? section.choices : null;
  return (
    <div id={`sec-${section.key}`} className="mt-6 scroll-mt-24 border-b pb-1 first:mt-0">
      <h3 className="flex flex-wrap items-center gap-2 text-base font-semibold">
        {sectionTitle(section.key)}
        <WriterBadges local={local} writer={writer} fallback={fallback} />
      </h3>
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
      {failed ? (
        <div className="mt-1 flex flex-wrap items-center gap-2 text-sm" role="status">
          <Badge variant="destructive">
            <AlertTriangle className="mr-1 size-3" aria-hidden="true" />
            생성 실패
          </Badge>
          <span className="text-muted-foreground">{failed.label} — 빈칸으로 두었습니다.</span>
          {onRegenerate && (
            <Button type="button" variant="outline" size="sm" onClick={() => onRegenerate(section.key)} aria-label={`${sectionTitle(section.key)} 이 섹션 다시 생성`}>
              <RefreshCw aria-hidden="true" />
              이 섹션 다시 생성
            </Button>
          )}
        </div>
      ) : (
        section.sentences.length === 0 && (
          <p className="mt-1 text-sm text-muted-foreground">
            {CHOICE_SECTIONS.has(section.key) ? "(본문 없이 체크 칸으로만 들어갑니다)" : "문장이 없습니다 — 근거·입력이 부족해 빈칸으로 둡니다. 직접 수정에서 채울 수 있습니다."}
          </p>
        )
      )}
    </div>
  );
}

function SentenceLine({
  row,
  citations,
  problem,
  onOpen,
}: {
  row: Extract<Row, { kind: "sentence" }>;
  citations: Citation[];
  problem?: string;
  /** 현재 버전일 때만 — 문장을 누르면 근거 패널 */
  onOpen?: (sid: string) => void;
}) {
  return (
    <div id={`sent-${row.key}`} className="flex scroll-mt-24 gap-2 py-1.5">
      <span className="w-6 shrink-0 pt-0.5 text-right text-xs tabular-nums text-muted-foreground" aria-hidden="true">
        {row.index + 1}
      </span>
      <div className="min-w-0 flex-1">
        {onOpen ? (
          <UntrustedText as="p" text={row.text} className="cursor-pointer rounded hover:bg-accent/60" onClick={() => onOpen(row.key)} />
        ) : (
          <UntrustedText as="p" text={row.text} />
        )}
        <div className="mt-1 flex flex-wrap items-center gap-1">
          <OriginBadge origin={row.origin} />
          {onOpen && (
            <Button type="button" variant="ghost" size="sm" className="h-6 px-1.5 text-xs" onClick={() => onOpen(row.key)} aria-label={`${sectionTitle(row.section)} 문장 ${row.index + 1} 근거 ${row.evidence.length}건 보기`}>
              근거 {row.evidence.length}건 보기
            </Button>
          )}
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
  const [params, setParams] = useSearchParams();
  const [evidenceSid, setEvidenceSid] = React.useState<string | null>(() => params.get("evidence"));
  const submitCheck = useSubmitCheck(id);
  const qc = useQueryClient();
  const { toast } = useToast();
  const [regenerateKey, setRegenerateKey] = React.useState<string | null>(null);
  const strategyDraft = (submitCheck.data?.items ?? []).some((i) => i.key === "strategy_source" && i.source === "draft");
  const openEvidence = (sid: string) => {
    setEvidenceSid(sid);
    setTab("current");
  };
  const closeEvidence = () => {
    setEvidenceSid(null);
    if (params.has("evidence")) {
      params.delete("evidence");
      setParams(params, { replace: true });
    }
  };
  // 제출 전 점검 → section:<key> 앵커로 들어오면 스크롤 (가상화 전이면 DOM 에 있다)
  React.useEffect(() => {
    if (!window.location.hash || draft.isPending) return;
    const el = document.getElementById(window.location.hash.slice(1));
    el?.scrollIntoView({ block: "start" });
    (el as HTMLElement | null)?.focus?.();
  }, [draft.isPending]);

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
  const failedByKey = new Map<string, FailedSection>((d.failed_sections ?? []).map((f) => [f.key, f]));
  const fallbackByKey = new Map<string, FallbackSection>((d.fallback_sections ?? []).map((f) => [f.key, f]));
  const localKeys = new Set(d.local_sections ?? []);
  const writers = d.writers ?? {};
  const localMismatchProblems = d.problems.filter((p) => p.code === LOCAL_EVIDENCE_MISMATCH).length;
  const localMismatches = Math.max(d.local_check?.mismatches ?? 0, localMismatchProblems);
  const sections: (DraftSection | VersionSection)[] = selected === null ? d.sections : (version.data?.sections ?? []);
  const figures = selected === null ? (d.figures ?? []) : (version.data?.figures ?? []);
  const rows = toRows(sections);
  const problemBySentence = new Map<string, string>();
  const problemsBySentence = new Map<string, Problem_[]>();
  const sectionProblems = d.problems.filter((p) => p.sentence === null);
  for (const p of d.problems)
    if (p.sentence !== null) {
      const sid = `s:${p.section}:${p.sentence}`;
      if (!problemBySentence.has(sid)) problemBySentence.set(sid, p.message);
      problemsBySentence.set(sid, [...(problemsBySentence.get(sid) ?? []), p]);
    }
  const evidenceRow = evidenceSid ? rows.find((r) => r.kind === "sentence" && r.key === evidenceSid) : undefined;

  const tabs = [{ id: "current", label: `현재 v${d.version}` }, ...versions.filter((v) => v !== d.version).map((v) => ({ id: String(v), label: `v${v}` }))];

  const renderRow = (row: Row) =>
    row.kind === "header" ? (
      <>
        <SectionHeader section={row.section} failed={selected === null ? failedByKey.get(row.section.key) : undefined} onRegenerate={selected === null ? setRegenerateKey : undefined} fallback={fallbackByKey.get(row.section.key)} local={localKeys.has(row.section.key)} writer={writers[row.section.key]} />
        {row.section.key !== "title" && (
          <div className="mt-3">
            <FigureList
              runId={id}
              figures={figures}
              section={row.section.key}
              baseVersion={d.version}
              readOnly
              disabled={selected !== null || d.flow.has_working || d.legacy}
              version={selected}
              onApplied={(v) => {
                toast(`v${v} 으로 저장했습니다 (그림)`, "success");
                qc.invalidateQueries({ queryKey: keys.run(id) });
              }}
            />
          </div>
        )}
      </>
    ) : (
      <SentenceLine row={row} citations={d.citations} problem={problemBySentence.get(row.key)} onOpen={selected === null ? openEvidence : undefined} />
    );

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="min-w-0 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">초안 본문</h2>
          <Link to={`/runs/${id}/edit`} className={buttonVariants({ variant: "outline", size: "sm" })}>
            직접 수정 →
          </Link>
        </div>
        <p className="text-xs text-muted-foreground">문장을 누르면 근거 원문·적합성을 보고 승인·교체·제외를 정할 수 있습니다 (현재 버전만).</p>
        {failedByKey.size > 0 && (
          <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm" role="alert">
            <p className="font-medium">생성 실패 섹션 {failedByKey.size}개 — 빈칸으로 두었습니다.</p>
            <p className="mt-1 text-muted-foreground">
              {[...failedByKey.values()].map((f) => `${sectionTitle(f.key)}(${f.label})`).join(", ")}. 섹션 머리의 [이 섹션 다시 생성]으로 로컬 모델에 다시 요청하거나 직접 수정에서 채우십시오.
            </p>
          </div>
        )}
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
          {d.local_check?.enabled && (
            <p className="mb-2 text-sm" data-testid="local-check">
              <Badge variant={localMismatches > 0 ? "warning" : "success"}>{LOCAL_EVIDENCE_MISMATCH_LABEL} {localMismatches}건</Badge>
              {d.local_check.skipped_sections.length > 0 && (
                <span className="ml-2 text-muted-foreground">대조 건너뜀: {d.local_check.skipped_sections.map(sectionTitle).join(", ")}</span>
              )}
            </p>
          )}
          {d.problems.length === 0 ? (
            <p className="text-sm text-muted-foreground">규칙 검사 알림이 없습니다.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {d.problems.map((p, i) => (
                <li key={i} className="flex flex-wrap gap-1">
                  <Badge variant={p.severity === "error" ? "destructive" : "warning"}>{p.severity}</Badge>
                  {p.code === LOCAL_EVIDENCE_MISMATCH && <Badge variant="outline">{LOCAL_EVIDENCE_MISMATCH_LABEL}</Badge>}
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
                  {c.live && <LiveBadge className="ml-1" />}
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

      <SectionRewrite
        runId={id}
        sectionKey={regenerateKey}
        baseVersion={d.version}
        dirty={d.flow.has_working}
        onClose={() => setRegenerateKey(null)}
        onApplied={(v) => {
          setRegenerateKey(null);
          toast(v === d.version ? "바뀐 내용이 없어 새 버전을 만들지 않았습니다." : `다시 생성한 섹션을 v${v} 으로 반영했습니다.`, "success");
          qc.invalidateQueries({ queryKey: keys.run(id) });
        }}
      />

      <EvidencePanel
        runId={id}
        sentenceId={evidenceSid}
        sentenceText={evidenceRow && evidenceRow.kind === "sentence" ? evidenceRow.text : undefined}
        citations={d.citations}
        problems={evidenceSid ? problemsBySentence.get(evidenceSid) ?? [] : []}
        baseVersion={d.version}
        strategyDraft={strategyDraft}
        onClose={closeEvidence}
      />
    </div>
  );
}
