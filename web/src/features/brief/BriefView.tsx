import { BookOpenCheck, Lightbulb } from "lucide-react";
import type { BriefOut } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { UntrustedText } from "@/components/UntrustedText";
import { basisLabel } from "@/lib/sections";
import { docRef, refSource, refTitle } from "@/lib/docRefs";
import { cn } from "@/lib/utils";

const SOURCE_LABELS: Record<string, string> = { alio: "알리오", openalex: "OpenAlex", scienceon: "ScienceON", ntis: "NTIS", own: "사내", kipris: "KIPRIS" };
const TYPE_LABELS: Record<string, string> = { paper: "논문", internal_report: "사내 보고서", rnd_project: "연구과제" };

/** 연도별 건수 — CSS 막대 (차트 라이브러리 없음). 막대는 장식, 수치는 글자로. */
export function YearBars({ years }: { years: Record<string, number> }) {
  const entries = Object.entries(years);
  if (entries.length === 0) return null;
  const max = Math.max(...entries.map(([, n]) => n), 1);
  return (
    <ul className="space-y-1" aria-label="연도별 건수">
      {entries.map(([y, n]) => (
        <li key={y} className="grid grid-cols-[3.5rem_1fr_2.5rem] items-center gap-2 text-sm">
          <span className="tabular-nums">{y}</span>
          <div className="h-3 rounded bg-muted" aria-hidden="true">
            <div className="h-3 rounded bg-primary" style={{ width: `${Math.round((n / max) * 100)}%` }} />
          </div>
          <span className="tabular-nums text-muted-foreground">{n}건</span>
        </li>
      ))}
    </ul>
  );
}

export interface BriefViewProps {
  brief: BriefOut;
  selected: string[];
  onToggle: (id: string, on: boolean) => void;
}

/** U5 선행연구 브리핑 — 10건 한 줄 요약(없으면 "요약 없음"), 연도별 건수, 주제어, 연구 공백 후보(후보 라벨).
 *  요약·공백 후보는 모델 출력(비신뢰). 체크한 항목은 생성 때 우선 근거(priority_evidence)로 보낸다. */
export function BriefView({ brief, selected, onToggle }: BriefViewProps) {
  const picked = new Set(selected);
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <section aria-labelledby="brief-items-h" className="min-w-0 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 id="brief-items-h" className="flex items-center gap-2 text-lg font-semibold">
            <BookOpenCheck className="size-5" aria-hidden="true" />
            선행연구 {brief.items.length}건
          </h2>
          <Badge variant="outline">
            {brief.provider ?? "—"} / {brief.model ?? "—"}
            {brief.fallback_local ? " (로컬 대체)" : ""}
          </Badge>
          <span className="text-xs text-muted-foreground">선택 {selected.length}건</span>
        </div>
        <p className="text-xs text-muted-foreground">
          외부 전송: 공개 자료 {brief.transfer.public_doc_ids.length}건, 사내 자료 {brief.transfer.internal_doc_ids.length}건, 호출 {brief.transfer.calls}회. 체크하면 초안 생성 때 그 자료를 근거로 앞세웁니다.
        </p>
        {brief.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">요약할 논문·보고서가 없습니다.</p>
        ) : (
          <ul className="space-y-2">
            {brief.items.map((it) => {
              const on = picked.has(it.chunk_id);
              return (
                <li key={it.chunk_id} className={cn("rounded-md border p-3", on && "border-primary")}>
                  <Label className="flex cursor-pointer items-start gap-2 font-normal">
                    <Checkbox checked={on} onChange={(e) => onToggle(it.chunk_id, e.target.checked)} className="mt-0.5" />
                    <span className="min-w-0 flex-1">
                      <UntrustedText as="span" text={it.title} className="font-medium" />
                      <span className="mt-1 flex flex-wrap gap-1 text-xs text-muted-foreground">
                        <Badge variant="secondary">{SOURCE_LABELS[it.source] ?? it.source}</Badge>
                        <Badge variant="outline">{TYPE_LABELS[it.doc_type] ?? it.doc_type}</Badge>
                        <span>{it.year ?? "연도 미상"}</span>
                        <span>· {basisLabel(it.basis)}</span>
                      </span>
                      <span className="mt-1 block text-sm">
                        {it.summary_missing ? <span className="text-muted-foreground">요약 없음</span> : <UntrustedText text={it.summary} />}
                      </span>
                    </span>
                  </Label>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <aside className="min-w-0 space-y-6">
        <section aria-labelledby="years-h" className="rounded-lg border p-3">
          <h2 id="years-h" className="mb-2 text-base font-semibold">연도별 건수</h2>
          {Object.keys(brief.years).length === 0 ? <p className="text-sm text-muted-foreground">없음</p> : <YearBars years={brief.years} />}
        </section>
        <section aria-labelledby="kw-h" className="rounded-lg border p-3">
          <h2 id="kw-h" className="mb-2 text-base font-semibold">주제어</h2>
          {brief.keywords.length === 0 ? (
            <p className="text-sm text-muted-foreground">없음</p>
          ) : (
            <ul className="flex flex-wrap gap-1" aria-label="주제어">
              {brief.keywords.map((k) => (
                <li key={k}>
                  <Badge variant="secondary" className="whitespace-normal">
                    <UntrustedText text={k} />
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section aria-labelledby="gaps-h" className="rounded-lg border p-3">
          <h2 id="gaps-h" className="mb-1 flex items-center gap-2 text-base font-semibold">
            <Lightbulb className="size-4" aria-hidden="true" />
            연구 공백 후보 {brief.gaps.length}건
          </h2>
          <p className="mb-2 text-xs text-muted-foreground">{brief.gap_label}</p>
          {brief.gaps.length === 0 ? (
            <p className="text-sm text-muted-foreground">자료에서 드러나는 공백 후보가 없습니다.</p>
          ) : (
            <ul className="space-y-2">
              {brief.gaps.map((g, i) => (
                <li key={i} className="rounded-md border border-dashed p-2 text-sm">
                  <Badge variant="warning" className="mb-1">후보</Badge>
                  <UntrustedText as="p" text={g.text} />
                  <p className="mt-1 text-xs text-muted-foreground">
                    근거:{" "}
                    {g.evidence
                      .map((id) => docRef(id, brief.items.map((it) => ({ id: it.chunk_id, doc_id: it.doc_id, title: it.title, source: it.source }))))
                      .map((r) => `${refTitle(r)} (${refSource(r)})`)
                      .filter((x, j, all) => all.indexOf(x) === j)
                      .join(", ")}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>
      </aside>
    </div>
  );
}
