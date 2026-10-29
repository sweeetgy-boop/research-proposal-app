import * as React from "react";
import { Award, ExternalLink } from "lucide-react";
import type { NtisOutcomesOut, NtisProjectInsight } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { UntrustedText } from "@/components/UntrustedText";

export const OUTCOMES_SHOWN = 5;
export const UNAVAILABLE_HINT = "NTIS 성과 조회 불가";

const KIND_LABEL: Record<string, string> = { paper: "논문", patent: "특허" };

export interface NtisInsightsProps {
  data: NtisOutcomesOut | null | undefined;
  loading?: boolean;
  /** 503(키 없음)·그 밖의 오류 — 한 줄 안내만, 흐름을 막지 않는다 */
  unavailable?: boolean;
}

function ProjectCard({ p }: { p: NtisProjectInsight }) {
  const [open, setOpen] = React.useState(false);
  const total = p.outcomes.length;
  const shown = open ? p.outcomes : p.outcomes.slice(0, OUTCOMES_SHOWN);
  const listId = `ntis-outcomes-${p.project_no}`;
  return (
    <Card data-testid="ntis-project">
      <CardHeader className="gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="info">{p.tier_label || "국가R&D 과제"}</Badge>
          {p.blocking ? <Badge variant="destructive">차단</Badge> : null}
        </div>
        <h3 className="text-base font-semibold leading-tight tracking-tight">
          <UntrustedText text={p.title} />
        </h3>
        {p.cached ? <p className="text-xs text-muted-foreground">저장해 둔 조회 결과</p> : null}
      </CardHeader>
      <CardContent className="space-y-2">
        <h4 className="text-sm font-semibold">주요 성과 (참고용)</h4>
        {p.error ? (
          <p className="text-sm text-muted-foreground">성과를 가져오지 못했습니다 ({p.error}).</p>
        ) : total === 0 ? (
          <p className="text-sm text-muted-foreground">등록된 논문·특허 성과가 없습니다.</p>
        ) : (
          <>
            <ul id={listId} className="space-y-1 text-sm">
              {shown.map((o, i) => (
                <li key={`${o.kind}-${o.result_id ?? i}`} className="flex flex-wrap items-baseline gap-x-2">
                  <Badge variant="secondary">{KIND_LABEL[o.kind] ?? o.kind}</Badge>
                  <UntrustedText text={o.title} className="font-medium" />
                  <span className="text-xs text-muted-foreground">
                    {[o.year, o.venue].filter(Boolean).map((v, j) => (
                      <React.Fragment key={j}>
                        {j > 0 ? " · " : ""}
                        <UntrustedText text={v} />
                      </React.Fragment>
                    ))}
                    {o.registration_no ? ` · ${o.registration_no}` : ""}
                  </span>
                </li>
              ))}
            </ul>
            {total > OUTCOMES_SHOWN ? (
              <Button variant="ghost" size="sm" aria-expanded={open} aria-controls={listId} onClick={() => setOpen((v) => !v)}>
                {open ? "접기" : `성과 ${total - OUTCOMES_SHOWN}건 더 보기`}
              </Button>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}

/** ② NTIS 과제 카드 — 주요 성과(참고용, 양식 근거 아님) + NTIS 추천(외부 링크·미검증). 전부 비신뢰 텍스트. */
export function NtisInsights({ data, loading, unavailable }: NtisInsightsProps) {
  const header = (
    <h2 className="flex items-center gap-2 text-lg font-semibold">
      <Award className="size-5" aria-hidden="true" />
      NTIS 과제 성과·추천
    </h2>
  );
  if (unavailable) {
    return (
      <section className="space-y-2" aria-label="NTIS 과제 성과·추천">
        {header}
        <p className="text-sm text-muted-foreground">{UNAVAILABLE_HINT}</p>
      </section>
    );
  }
  if (loading) {
    return (
      <section className="space-y-2" aria-busy="true" aria-label="NTIS 과제 성과·추천">
        {header}
        <SkeletonBlock lines={3} />
      </section>
    );
  }
  if (!data) return null;
  if (data.projects.length === 0 && data.ntis_recommended.length === 0) return null;
  return (
    <section className="space-y-4" aria-label="NTIS 과제 성과·추천">
      {header}
      <p className="text-sm text-muted-foreground">
        유사과제 중 국가R&D 과제의 논문·특허 성과와 NTIS 가 제안한 연관 과제입니다. 참고용이며 양식 근거로 쓰지 않습니다.
      </p>
      {data.projects.length > 0 ? (
        <div className="grid gap-3 md:grid-cols-2">
          {data.projects.map((p) => (
            <ProjectCard key={p.doc_id} p={p} />
          ))}
        </div>
      ) : null}
      {data.ntis_recommended.length > 0 ? (
        <div className="space-y-2 rounded-lg border bg-card p-4" data-testid="ntis-recommended">
          <h3 className="text-sm font-semibold">NTIS 추천</h3>
          <p className="text-xs text-muted-foreground">외부 링크 · 미검증 — 제목·순위는 NTIS 응답을 그대로 보인 것이며 내용은 확인하지 않았습니다.</p>
          <ol className="space-y-1 text-sm">
            {data.ntis_recommended.map((r) => (
              <li key={r.project_no} className="flex flex-wrap items-baseline gap-x-2">
                <a href={r.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline underline-offset-2">
                  <UntrustedText text={r.title} />
                  <ExternalLink className="size-3.5" aria-hidden="true" />
                  <span className="sr-only">(외부 링크, 새 창)</span>
                </a>
                {/* 과제번호·점수 숫자는 보이지 않는다 (ADR 0039 — ② 화면 내부 번호 없음). 순위만 */}
                {r.rank != null && <span className="text-xs text-muted-foreground tabular-nums">NTIS 추천 {r.rank}위</span>}
              </li>
            ))}
          </ol>
        </div>
      ) : null}
      <p className="text-xs text-muted-foreground">
        <UntrustedText text={data.notice} />
      </p>
    </section>
  );
}
