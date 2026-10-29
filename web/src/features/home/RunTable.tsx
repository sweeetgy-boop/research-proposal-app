/** 제안서 표 — 홈 "최근 제안서"와 내 제안서 화면이 함께 쓴다. 탭(전체·작성 중·완료)·제목 검색·정렬,
 *  줄마다 문서 타일·제목·과제유형·수정 시각·상태 칩·진행률(6단계)·"⋯" 메뉴(이미 있는 화면으로 가는 링크만).
 *  제목은 모델 출력일 수 있어 글자로만 그린다. */
import * as React from "react";
import { Link } from "react-router";
import { ArrowRight, FileText, MoreHorizontal, Search } from "lucide-react";
import type { RunState } from "@/api/types";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { TabPanel, Tabs } from "@/components/ui/tabs";
import { isGenerated } from "@/lib/runSteps";
import { cn, formatDate } from "@/lib/utils";
import { ProgressBar } from "@/components/ui/progress-bar";
import { StatusChip } from "@/components/ui/status-chip";
import {
  chipLabel,
  chipStatus,
  continuePath,
  displayTitle,
  progressPercent,
  progressText,
  relativeEdited,
  RUN_SORTS,
  runCounts,
  visibleRuns,
  type RunSort,
  type RunTab,
} from "./runView";

const TILES = [
  "bg-primary-soft text-primary-soft-foreground",
  "bg-mint text-mint-foreground",
  "bg-apricot text-apricot-foreground",
];

export interface RunTableProps {
  runs: RunState[];
  /** 제목 (h2/h1 글자) */
  title: string;
  headingLevel?: "h1" | "h2";
  /** 홈: 앞 몇 줄만 — 없으면 전부 */
  limit?: number;
  /** 홈: 오른쪽 위 "전체 보기 →" */
  showAllLink?: boolean;
  /** 내 제안서: 줄 정보에 작성 번호(오류 보고용) */
  showRunId?: boolean;
  guest?: boolean;
  /** 표 오른쪽 위 추가 동작 (내 제안서의 [새 제안서]) */
  actions?: React.ReactNode;
}

export function RunTable({ runs, title, headingLevel = "h2", limit, showAllLink, showRunId, guest, actions }: RunTableProps) {
  const [tab, setTab] = React.useState<RunTab>("all");
  const [query, setQuery] = React.useState("");
  const [sort, setSort] = React.useState<RunSort>("recent");
  const counts = runCounts(runs);
  const rows = visibleRuns(runs, tab, query, sort);
  const shown = limit ? rows.slice(0, limit) : rows;
  const Heading = headingLevel;
  const baseId = React.useId().replace(/:/g, "");
  const tabs = [
    { id: `${baseId}-all`, key: "all" as const, label: "전체", count: counts.all },
    { id: `${baseId}-writing`, key: "writing" as const, label: "작성 중", count: counts.writing },
    { id: `${baseId}-done`, key: "done" as const, label: "완료", count: counts.done },
  ];
  const activeId = tabs.find((t) => t.key === tab)!.id;

  return (
    <section aria-labelledby={`${baseId}-title`} className="rounded-xl border bg-card shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-5">
        <div className="flex items-center gap-2">
          <Heading id={`${baseId}-title`} className={cn("font-bold tracking-tight", headingLevel === "h1" ? "text-2xl" : "text-lg")}>
            {title}
          </Heading>
          <span className="rounded-md bg-primary-soft px-2 py-0.5 text-xs font-semibold tabular-nums text-primary-soft-foreground">
            <span className="sr-only">전체 </span>
            {counts.all}
            <span className="sr-only">건</span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          {actions}
          {showAllLink && (
            <Link to="/runs" className="inline-flex min-h-10 items-center gap-1 text-sm font-semibold text-primary underline-offset-4 hover:underline">
              전체 보기
              <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
          )}
        </div>
      </div>
      <div className="px-5">
        <Tabs
          label={`${title} 거르기`}
          items={tabs.map(({ id, label, count }) => ({ id, label, count }))}
          value={activeId}
          onChange={(id) => setTab(tabs.find((t) => t.id === id)!.key)}
          className="mt-3"
        />
      </div>
      <TabPanel id={activeId} active className="pt-0">
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
          <div className="relative w-full sm:w-72">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="제목으로 검색"
              aria-label="제안서 제목 검색"
              className="pl-9"
            />
          </div>
          <Select aria-label="정렬" value={sort} onChange={(e) => setSort(e.target.value as RunSort)} className="w-full sm:w-40">
            {RUN_SORTS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </Select>
        </div>
        <div aria-hidden="true" className="hidden grid-cols-[minmax(0,1fr)_7rem_9rem_2.5rem] gap-4 border-b px-5 pb-2 text-xs font-medium text-muted-foreground md:grid">
          <span>제안서 제목</span>
          <span>상태</span>
          <span>진행률</span>
          <span />
        </div>
        {shown.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-muted-foreground">
            {runs.length === 0 ? "아직 만든 제안서가 없습니다. [새 제안서]에서 시작하세요." : "조건에 맞는 제안서가 없습니다."}
          </p>
        ) : (
          <ul aria-label={`${title} 목록`} data-testid="run-rows">
            {shown.map((r, i) => (
              <RunRow key={r.run_id} run={r} tile={TILES[i % TILES.length]!} showRunId={showRunId} />
            ))}
          </ul>
        )}
      </TabPanel>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t px-5 py-3 text-xs text-muted-foreground">
        <span>
          {runs.length}개의 제안서 중 {shown.length}개 표시
        </span>
        <span className="text-right">
          제안서는 연구원 서버에 저장됩니다.
          {guest && <span className="block font-medium text-foreground" data-testid="guest-notice">공용 계정의 제안서는 함께 쓰는 사람에게 보입니다.</span>}
        </span>
      </div>
    </section>
  );
}

function RunRow({ run, tile, showRunId }: { run: RunState; tile: string; showRunId?: boolean }) {
  const title = displayTitle(run);
  const pct = progressPercent(run);
  const info = [run.task_type, relativeEdited(run.updated_at)].filter(Boolean).join(" · ");
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_2.5rem] items-center gap-x-4 gap-y-2 border-b px-5 py-4 last:border-b-0 md:grid-cols-[minmax(0,1fr)_7rem_9rem_2.5rem]">
      <div className="flex min-w-0 items-start gap-3">
        <span className={cn("grid size-10 shrink-0 place-items-center rounded-xl", tile)}>
          <FileText className="size-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <Link
            to={continuePath(run)}
            title={run.title || undefined}
            className="line-clamp-2 break-words font-semibold text-foreground underline-offset-2 hover:text-primary hover:underline"
          >
            {title}
          </Link>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {info}
            {run.legacy && " · 예전 방식"}
            {run.flow?.stale && ` · 수정 ${run.flow.stale_edits}건`}
          </p>
          {showRunId && (
            <p className="text-xs text-muted-foreground">
              만든 때 {formatDate(run.created_at)} · <span className="sr-only">작성 번호 </span>
              <span className="font-mono">{run.run_id}</span>
            </p>
          )}
        </div>
      </div>
      <div className="col-start-1 row-start-2 flex items-center gap-3 pl-13 md:col-start-auto md:row-start-auto md:block md:pl-0">
        <StatusChip status={chipStatus(run)}>{chipLabel(run) ?? undefined}</StatusChip>
      </div>
      <div className="col-start-1 row-start-3 pl-13 md:col-start-auto md:row-start-auto md:pl-0">
        <div className="max-w-40" title={progressText(run)}>
          <ProgressBar value={pct} label={`「${title}」 진행률 — ${progressText(run)}`} />
        </div>
      </div>
      <div className="col-start-2 row-span-3 row-start-1 self-start md:col-start-auto md:row-span-1 md:row-start-auto md:self-center">
        <RowMenu run={run} title={title} />
      </div>
    </li>
  );
}

/** "⋯" 메뉴 — 이어서 작성·진행 상황·초안 보기(만든 뒤). Esc·바깥 누르면 닫힌다. */
function RowMenu({ run, title }: { run: RunState; title: string }) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);
  const btn = React.useRef<HTMLButtonElement>(null);
  const menuId = React.useId();
  React.useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);
  const items = [
    { to: continuePath(run), label: "이어서 작성" },
    { to: `/runs/${run.run_id}`, label: "진행 상황" },
    ...(isGenerated(run) ? [{ to: `/runs/${run.run_id}/draft`, label: "초안 보기" }] : []),
  ];
  return (
    <div
      ref={ref}
      className="relative"
      onKeyDown={(e) => {
        if (e.key === "Escape" && open) {
          e.stopPropagation();
          setOpen(false);
          btn.current?.focus();
        }
      }}
      onBlur={(e) => {
        if (!ref.current?.contains(e.relatedTarget as Node)) setOpen(false);
      }}
    >
      <button
        ref={btn}
        type="button"
        aria-label={`「${title}」 메뉴`}
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((v) => !v)}
        className="grid size-10 place-items-center rounded-lg text-muted-foreground hover:bg-accent hover:text-foreground"
      >
        <MoreHorizontal className="size-5" aria-hidden="true" />
      </button>
      {open && (
        <ul id={menuId} className="absolute right-0 z-20 mt-1 w-40 rounded-xl border bg-card p-1 shadow-lg">
          {items.map((it) => (
            <li key={it.label}>
              <Link to={it.to} className="flex min-h-10 items-center rounded-lg px-3 text-sm hover:bg-accent" onClick={() => setOpen(false)}>
                {it.label}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
