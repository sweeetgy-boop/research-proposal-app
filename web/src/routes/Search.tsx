/** 자료 검색 — 위쪽 통합 검색 [자료 전체 결과 보기] 가 여는 전체 결과 (2026-10-29 [UI] 레인 3).
 *  주소가 상태다: /search?q=…&sources=a,b&year_from=…&year_to=… (뒤로 가기·공유 그대로).
 *  문서 하나가 한 줄(제목·자료원·연도·발췌), 누르면 근거 패널(요약·원문 링크). 공용 계정은 서버가 internal 을 뺀다. */
import * as React from "react";
import { ExternalLink, Library, Search as SearchIcon } from "lucide-react";
import { useSearchParams } from "react-router";
import { useSources } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Eyebrow } from "@/components/ui/eyebrow";
import { Checkbox } from "@/components/ui/checkbox";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { EmptyState } from "@/components/EmptyState";
import { UntrustedText } from "@/components/UntrustedText";
import { DocRefPanel } from "@/components/DocRef";
import { LiveBadge } from "@/features/live/LiveBadge";
import { type DocHit, useDocSearch } from "@/features/globalsearch/api";
import { hasInternalId, refTitle } from "@/lib/docRefs";
import { basisLabel } from "@/lib/sections";

const LIMIT = 20;

const toYear = (v: string | null): number | null => {
  const n = Number(v);
  return v && Number.isInteger(n) && n >= 1900 && n <= 2100 ? n : null;
};

export default function Search() {
  const [params, setParams] = useSearchParams();
  const q = (params.get("q") ?? "").trim();
  const sources = React.useMemo(() => (params.get("sources") ?? "").split(",").filter(Boolean), [params]);
  const yearFrom = toYear(params.get("year_from"));
  const yearTo = toYear(params.get("year_to"));
  // 근거 패널 [원본 보기] 는 문서 번호로 연다 — 번호는 입력칸에 보이지 않는다
  const byId = hasInternalId(q);
  const [input, setInput] = React.useState(byId ? "" : q);
  const [from, setFrom] = React.useState(yearFrom ? String(yearFrom) : "");
  const [to, setTo] = React.useState(yearTo ? String(yearTo) : "");
  const [panel, setPanel] = React.useState<DocHit | null>(null);
  React.useEffect(() => setInput(byId ? "" : q), [q, byId]);

  const src = useSources();
  const options = (src.data?.sources ?? []).filter((s) => s.count > 0);
  const res = useDocSearch({ q, limit: LIMIT, sources, yearFrom, yearTo });
  const yearError = yearFrom && yearTo && yearFrom > yearTo ? "시작 연도가 끝 연도보다 늦습니다." : null;

  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    setParams(next);
  };
  const toggleSource = (key: string, on: boolean) => {
    const set = new Set(sources);
    if (on) set.add(key);
    else set.delete(key);
    update({ sources: [...set].join(",") || null });
  };
  const filtered = sources.length > 0 || yearFrom !== null || yearTo !== null;

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <Eyebrow>Library</Eyebrow>
        <h1 className="text-2xl font-bold tracking-tight">자료 검색</h1>
        <p className="text-sm text-muted-foreground">
          사내 과제·공시 요약·논문·특허·공고를 키워드와 의미로 함께 찾습니다. 결과는 수집 자료(비신뢰 텍스트)이므로 원문에서 확인한 뒤 씁니다.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[16rem_minmax(0,1fr)]">
        <aside aria-label="검색 조건" className="space-y-4 rounded-xl border bg-card p-4 shadow-card lg:self-start">
          <form
            role="search"
            className="space-y-2"
            onSubmit={(e) => {
              e.preventDefault();
              update({ q: input.trim() || null });
            }}
          >
            <Label htmlFor="q">검색어</Label>
            <Input id="q" value={input} onChange={(e) => setInput(e.target.value)} maxLength={500} placeholder="예: 궤도 틀림 예측" />
            <Button type="submit" className="w-full" disabled={!input.trim()}>
              <SearchIcon aria-hidden="true" />
              검색
            </Button>
          </form>

          <div className="border-t pt-4">
            <fieldset className="space-y-2">
              <legend className="mb-2 text-sm font-semibold">자료원</legend>
              {src.isPending && <SkeletonBlock lines={3} />}
              {src.error && <p className="text-sm text-destructive">자료원 목록을 불러오지 못했습니다.</p>}
              {options.length === 0 && src.data && <p className="text-sm text-muted-foreground">적재된 자료원이 없습니다.</p>}
              <ul className="space-y-1.5">
                {options.map((s) => (
                  <li key={s.source}>
                    <label className="flex min-h-8 cursor-pointer items-center gap-2 text-sm">
                      <Checkbox checked={sources.includes(s.source)} onChange={(e) => toggleSource(s.source, e.target.checked)} />
                      <span className="min-w-0 flex-1">{s.label}</span>
                      <span className="tabular-nums text-xs text-muted-foreground">{s.count.toLocaleString("ko-KR")}</span>
                    </label>
                  </li>
                ))}
              </ul>
            </fieldset>
          </div>

          <div className="border-t pt-4">
            <fieldset className="space-y-2">
              <legend className="mb-2 text-sm font-semibold">발행 연도</legend>
              <form
                className="space-y-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  update({ year_from: toYear(from) ? from : null, year_to: toYear(to) ? to : null });
                }}
              >
                <div className="flex items-end gap-2">
                  <div className="min-w-0 flex-1 space-y-1">
                    <Label htmlFor="year-from" className="text-xs">
                      시작
                    </Label>
                    <Input id="year-from" inputMode="numeric" pattern="[0-9]{4}" value={from} onChange={(e) => setFrom(e.target.value)} />
                  </div>
                  <span aria-hidden="true" className="pb-2 text-muted-foreground">
                    ~
                  </span>
                  <div className="min-w-0 flex-1 space-y-1">
                    <Label htmlFor="year-to" className="text-xs">
                      끝
                    </Label>
                    <Input id="year-to" inputMode="numeric" pattern="[0-9]{4}" value={to} onChange={(e) => setTo(e.target.value)} />
                  </div>
                </div>
                <Button type="submit" variant="outline" size="sm" className="w-full">
                  연도 적용
                </Button>
              </form>
              <p className="text-xs text-muted-foreground">연도를 정하면 발행 연도를 모르는 자료는 빠집니다.</p>
            </fieldset>
          </div>

          {filtered && (
            <Button
              variant="ghost"
              size="sm"
              className="w-full"
              onClick={() => {
                setFrom("");
                setTo("");
                update({ sources: null, year_from: null, year_to: null });
              }}
            >
              조건 지우기
            </Button>
          )}
        </aside>

        <section aria-labelledby="search-results-title" className="min-w-0 rounded-xl border bg-card shadow-card">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3 sm:px-5">
            <h2 id="search-results-title" className="text-base font-semibold">
              검색 결과
              {res.data && (
                <span className="ml-2 rounded-full bg-primary-soft px-2 py-0.5 text-xs font-semibold text-primary-soft-foreground tabular-nums">{res.data.docs.length}</span>
              )}
            </h2>
            {q && !byId && <p className="text-sm text-muted-foreground">「{q}」</p>}
          </div>
          <div aria-live="polite" className="min-h-40 p-4 sm:p-5">
            {!q && <EmptyState icon={Library} title="검색어를 입력하십시오" description="위쪽 통합 검색(⌘K / Ctrl+K)에서도 바로 찾을 수 있습니다." />}
            {yearError && <p className="text-sm text-destructive">{yearError}</p>}
            {res.isFetching && !res.data && <SkeletonBlock lines={4} />}
            <ProblemBanner error={res.error} onRetry={() => res.refetch()} />
            {res.data && res.data.docs.length === 0 && (
              <EmptyState title="결과 없음" description={filtered ? "자료원·연도 조건을 넓히거나 다른 검색어로 찾아보십시오." : "다른 검색어로 다시 찾아보십시오."} />
            )}
            {res.data && res.data.docs.length > 0 && (
              <ol className="divide-y" data-testid="search-results">
                {res.data.docs.map((d) => (
                  <li key={d.doc_id} className="py-3 first:pt-0 last:pb-0">
                    <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                      {/* 내부 문서 번호는 보이지 않는다 — 자료원 이름·연도·본문 종류만 */}
                      <span className="font-medium text-foreground/80">{d.source_label}</span>
                      {d.year && <span>· {d.year}년</span>}
                      {d.basis && <Badge variant="secondary">{basisLabel(d.basis)}</Badge>}
                      {d.live && <LiveBadge />}
                      <Badge variant="warning">비신뢰</Badge>
                    </div>
                    <button
                      type="button"
                      onClick={() => setPanel(d)}
                      className="mt-1 text-left text-base font-semibold text-foreground underline-offset-2 hover:text-primary hover:underline focus-visible:outline-2 focus-visible:outline-ring"
                      aria-label={`${refTitle(d)} 요약 보기`}
                    >
                      {refTitle(d)}
                    </button>
                    {d.summary && <UntrustedText as="p" text={d.summary} className="mt-1 line-clamp-3 text-sm text-muted-foreground" />}
                    {d.url && (
                      <a href={d.url} target="_blank" rel="noreferrer noopener" className="mt-1 inline-flex items-center gap-1 text-sm text-primary underline-offset-2 hover:underline">
                        원문 보기 <ExternalLink className="size-3" aria-hidden="true" />
                        <span className="sr-only">(새 창)</span>
                      </a>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </div>
        </section>
      </div>
      {panel && <DocRefPanel docRef={panel} open onClose={() => setPanel(null)} />}
    </div>
  );
}
