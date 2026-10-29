/** 위쪽 통합 검색 (2026-10-29 [UI] 레인 3) — 내 제안서 제목과 수집 자료를 함께 찾는다.
 *
 * - ⌘K / Ctrl+K 로 어디서든 연다. 입력하는 대로(0.25초 뒤) 두 묶음: "내 제안서" 최대 5건, "자료" 상위 5건.
 * - 키보드: ↑/↓ 두 묶음과 [자료 전체 결과 보기] 를 오간다, Enter 열기, Esc 닫기(포커스는 입력칸).
 * - 제안서 → 그 제안서의 현재 단계 화면. 자료 → 근거 패널(요약·원문 링크). 전체 결과 → 자료 검색(/search?q=…).
 * - 로그인 전에는 결과를 부르지 않고 로그인 창으로 보낸다. 공용 계정은 서버가 internal 자료를 뺀다.
 * - ARIA 1.2 combobox + listbox(group 둘 + 전체 결과 option). 내부 문서 번호는 보이지 않는다.
 */
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, FileText, Library, Search as SearchIcon } from "lucide-react";
import { useLocation, useNavigate } from "react-router";
import * as api from "@/api/endpoints";
import { isApiError } from "@/api/client";
import type { RunState } from "@/api/types";
import { keys } from "@/api/hooks";
import { useLoggedIn } from "@/auth/useSession";
import { DocRefPanel } from "@/components/DocRef";
import { LiveBadge } from "@/features/live/LiveBadge";
import { refTitle } from "@/lib/docRefs";
import { statusLabel } from "@/lib/sections";
import { cn, formatDate } from "@/lib/utils";
import { type DocHit, useDocSearch } from "./api";
import { matchProposals, proposalPath } from "./match";

const DEBOUNCE_MS = 250;
const PROPOSALS = 5;
const DOCS = 5;

type Item =
  | { kind: "proposal"; id: string; run: RunState }
  | { kind: "doc"; id: string; doc: DocHit }
  | { kind: "all"; id: string };

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = React.useState(value);
  React.useEffect(() => {
    const t = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return v;
}

const isMac = () => typeof navigator !== "undefined" && /Mac|iPhone|iPad/i.test(navigator.platform || navigator.userAgent);

function errorReason(e: unknown): string {
  if (isApiError(e)) return e.problem.detail || e.problem.title;
  if (e instanceof Error) return e.message === "Failed to fetch" ? "서버에 연결할 수 없습니다." : e.message;
  return "요청을 처리하지 못했습니다.";
}

/** 로그인 전 — 로그인 화면으로 보내고 지금 주소를 기억한다 (레인 1 의 화면 안 로그인 창이 들어오면 그것으로 바꾼다). */
function useOpenLogin() {
  const navigate = useNavigate();
  const location = useLocation();
  return React.useCallback(() => {
    if (location.pathname === "/login") return;
    navigate("/login", { state: { from: location.pathname + location.search } });
  }, [navigate, location.pathname, location.search]);
}

export function GlobalSearch({ className }: { className?: string }) {
  const loggedIn = useLoggedIn();
  const openLogin = useOpenLogin();
  const navigate = useNavigate();
  const inputRef = React.useRef<HTMLInputElement>(null);
  const rootRef = React.useRef<HTMLDivElement>(null);
  const [text, setText] = React.useState("");
  const [open, setOpen] = React.useState(false);
  const [active, setActive] = React.useState(-1);
  const [panelDoc, setPanelDoc] = React.useState<DocHit | null>(null);
  const q = useDebounced(text.trim(), DEBOUNCE_MS);
  const ids = React.useId();
  const listboxId = `${ids}-listbox`;
  const optId = (i: number) => `${ids}-opt-${i}`;
  const mac = React.useMemo(isMac, []);

  const runs = useQuery({ queryKey: keys.runs, queryFn: () => api.listRuns(50), enabled: loggedIn && open });
  const docs = useDocSearch({ q, limit: DOCS }, loggedIn && open);

  const proposals = React.useMemo(() => matchProposals(runs.data?.runs ?? [], text.trim(), text.trim() ? PROPOSALS : 3), [runs.data, text]);
  const docHits = q ? (docs.data?.docs ?? []) : [];
  const items: Item[] = React.useMemo(() => {
    const out: Item[] = proposals.map((run) => ({ kind: "proposal", id: run.run_id, run }));
    for (const doc of docHits) out.push({ kind: "doc", id: doc.doc_id, doc });
    if (text.trim()) out.push({ kind: "all", id: "all" });
    return out;
  }, [proposals, docHits, text]);

  // 결과가 바뀌면 선택을 처음으로
  React.useEffect(() => setActive(-1), [q, proposals.length]);

  // ⌘K / Ctrl+K — 어디서든
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.altKey || e.shiftKey || e.key.toLowerCase() !== "k") return;
      e.preventDefault();
      if (!loggedIn) {
        openLogin();
        return;
      }
      inputRef.current?.focus();
      inputRef.current?.select();
      setOpen(true);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [loggedIn, openLogin]);

  // 바깥을 누르면 닫는다
  React.useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, [open]);

  const close = () => {
    setOpen(false);
    setActive(-1);
  };

  const activate = (item: Item) => {
    close();
    if (item.kind === "proposal") navigate(proposalPath(item.run));
    else if (item.kind === "doc") setPanelDoc(item.doc);
    else navigate(`/search?q=${encodeURIComponent(text.trim())}`);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      if (open) {
        e.preventDefault();
        close();
      }
      return;
    }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      if (items.length === 0) return;
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActive((a) => (a < 0 ? (step > 0 ? 0 : items.length - 1) : (a + step + items.length) % items.length));
      return;
    }
    if (e.key === "Home" && open && items.length) {
      e.preventDefault();
      setActive(0);
      return;
    }
    if (e.key === "End" && open && items.length) {
      e.preventDefault();
      setActive(items.length - 1);
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      const item = active >= 0 ? items[active] : text.trim() ? items.find((i) => i.kind === "all") : undefined;
      if (item) activate(item);
    }
  };

  // 선택된 항목이 보이게
  React.useEffect(() => {
    if (active < 0) return;
    document.getElementById(optId(active))?.scrollIntoView?.({ block: "nearest" });
  }, [active]);

  const docsLoading = !!q && docs.isFetching && !docs.data;
  const typing = text.trim() !== q;
  const status = !open
    ? ""
    : docs.error
      ? `제안서 ${proposals.length}건. 자료를 불러오지 못했습니다.`
      : text.trim() && !typing && !docsLoading
        ? `제안서 ${proposals.length}건, 자료 ${docHits.length}건`
        : "";

  const indexOf = (kind: Item["kind"], id: string) => items.findIndex((i) => i.kind === kind && i.id === id);
  const optionClass = (i: number) =>
    cn(
      "flex w-full cursor-pointer items-start gap-3 rounded-lg px-3 py-2 text-left text-sm",
      i === active ? "bg-accent text-accent-foreground" : "hover:bg-muted",
    );

  return (
    <div ref={rootRef} className={cn("relative w-full sm:w-80", className)}>
      <div className="relative">
        <SearchIcon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
        <input
          ref={inputRef}
          type="search"
          role="combobox"
          aria-label="제안서·자료 통합 검색"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-haspopup="listbox"
          aria-activedescendant={open && active >= 0 ? optId(active) : undefined}
          aria-keyshortcuts="Meta+K Control+K"
          placeholder="제안서·자료 검색"
          autoComplete="off"
          spellCheck={false}
          maxLength={200}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            if (loggedIn) setOpen(true);
          }}
          onFocus={() => {
            if (!loggedIn) openLogin();
            else setOpen(true);
          }}
          onKeyDown={onKeyDown}
          className="h-10 w-full rounded-lg border border-input bg-muted/40 pl-9 pr-16 text-sm text-foreground placeholder:text-muted-foreground focus-visible:bg-background focus-visible:outline-2 focus-visible:outline-ring [&::-webkit-search-cancel-button]:hidden"
        />
        <kbd
          aria-hidden="true"
          className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rounded-md border bg-card px-1.5 py-0.5 font-sans text-xs font-medium text-muted-foreground"
        >
          {mac ? "⌘K" : "Ctrl K"}
        </kbd>
      </div>
      <p className="sr-only" role="status" aria-live="polite">
        {status}
      </p>
      <div
        className={cn(
          "z-50 mt-2 overflow-hidden rounded-xl border bg-card text-card-foreground shadow-lg",
          "max-sm:fixed max-sm:inset-x-2 max-sm:top-16 sm:absolute sm:right-0 sm:w-[min(92vw,34rem)]",
          !open && "hidden",
        )}
      >
        <div id={listboxId} role="listbox" aria-label="통합 검색 결과" className="max-h-[min(70vh,32rem)] overflow-y-auto p-2">
          <div role="group" aria-labelledby={`${ids}-g-p`} className="pb-1">
            <div id={`${ids}-g-p`} role="presentation" className="flex items-center gap-1.5 px-3 pb-1 pt-1.5 text-xs font-semibold text-muted-foreground">
              <FileText className="size-3.5" aria-hidden="true" />
              {text.trim() ? "내 제안서" : "최근 제안서"}
            </div>
            {runs.isPending && open && <p className="px-3 py-2 text-sm text-muted-foreground">제안서 목록을 불러오는 중…</p>}
            {runs.error && <p className="px-3 py-2 text-sm text-destructive">제안서 목록을 불러오지 못했습니다: {errorReason(runs.error)}</p>}
            {runs.data && proposals.length === 0 && (
              <p className="px-3 py-2 text-sm text-muted-foreground">
                {runs.data.runs.length === 0 ? "아직 만든 제안서가 없습니다." : "제목이 맞는 제안서가 없습니다."}
              </p>
            )}
            {proposals.map((run) => {
              const i = indexOf("proposal", run.run_id);
              return (
                <div
                  key={run.run_id}
                  id={optId(i)}
                  role="option"
                  aria-selected={i === active}
                  className={optionClass(i)}
                  onPointerMove={() => setActive(i)}
                  onClick={() => activate(items[i]!)}
                >
                  <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-md bg-accent text-primary">
                    <FileText className="size-4" aria-hidden="true" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{run.title?.trim() || "제목 미정"}</span>
                    <span className="block text-xs text-muted-foreground">
                      {statusLabel(run.status)} · {formatDate(run.updated_at)} 수정
                    </span>
                  </span>
                </div>
              );
            })}
          </div>
          {text.trim() && (
            <div role="group" aria-labelledby={`${ids}-g-d`} className="border-t pt-1">
              <div id={`${ids}-g-d`} role="presentation" className="flex items-center gap-1.5 px-3 pb-1 pt-1.5 text-xs font-semibold text-muted-foreground">
                <Library className="size-3.5" aria-hidden="true" />
                자료
              </div>
              {(typing || docsLoading) && !docs.error && <p className="px-3 py-2 text-sm text-muted-foreground">자료를 찾는 중…</p>}
              {docs.error && !typing && <p className="px-3 py-2 text-sm text-destructive">자료를 불러오지 못했습니다: {errorReason(docs.error)}</p>}
              {!typing && docs.data && docHits.length === 0 && (
                <p className="px-3 py-2 text-sm text-muted-foreground">맞는 자료가 없습니다. 다른 낱말로 찾아보십시오.</p>
              )}
              {!typing &&
                docHits.map((doc) => {
                  const i = indexOf("doc", doc.doc_id);
                  return (
                    <div
                      key={doc.doc_id}
                      id={optId(i)}
                      role="option"
                      aria-selected={i === active}
                      className={optionClass(i)}
                      onPointerMove={() => setActive(i)}
                      onClick={() => activate(items[i]!)}
                    >
                      <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground">
                        <Library className="size-4" aria-hidden="true" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium">{refTitle(doc)}</span>
                        <span className="flex flex-wrap items-center gap-x-1 text-xs text-muted-foreground">
                          {doc.source_label}
                          {doc.year && <span>· {doc.year}년</span>}
                          {doc.live && <LiveBadge className="ml-1" />}
                        </span>
                      </span>
                    </div>
                  );
                })}
            </div>
          )}
          {text.trim() &&
            (() => {
              const i = indexOf("all", "all");
              return (
                <div
                  id={optId(i)}
                  role="option"
                  aria-selected={i === active}
                  className={cn(optionClass(i), "mt-1 items-center border-t font-medium text-primary")}
                  onPointerMove={() => setActive(i)}
                  onClick={() => activate(items[i]!)}
                >
                  <span className="flex-1">자료 전체 결과 보기</span>
                  <ArrowRight className="size-4" aria-hidden="true" />
                </div>
              );
            })()}
        </div>
        <p className="border-t bg-muted/40 px-4 py-2 text-xs text-muted-foreground">↑↓ 이동 · Enter 열기 · Esc 닫기 · 자료는 수집 자료(비신뢰)입니다</p>
      </div>
      {panelDoc && (
        <DocRefPanel
          docRef={panelDoc}
          open
          onClose={() => {
            setPanelDoc(null);
            window.setTimeout(() => inputRef.current?.focus(), 0);
          }}
        />
      )}
    </div>
  );
}
