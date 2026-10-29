import * as React from "react";
import { ChevronRight, CircleHelp, Home, Menu, Search } from "lucide-react";
import { Link, useLocation } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { getRun } from "@/api/endpoints";
import { keys } from "@/api/hooks";
import { useLoggedIn } from "@/auth/useSession";
import { useRequireLogin } from "@/features/auth/useRequireLogin";
import { cn } from "@/lib/utils";
import { crumbsFor } from "./crumbs";

/** 제안서 안이면 제목 — RunLayout 과 같은 캐시 키라 따로 부르지 않는다. 로그인 전에는 부르지 않는다. */
function useRunTitle(pathname: string): string | null {
  const id = /^\/runs\/([^/]+)/.exec(pathname)?.[1] ?? "";
  const loggedIn = useLoggedIn();
  const q = useQuery({ queryKey: keys.run(id), queryFn: () => getRun(id), enabled: loggedIn && id !== "" });
  return id && q.data ? (q.data.title ?? null) : null;
}

export function Breadcrumb() {
  const { pathname } = useLocation();
  const title = useRunTitle(pathname);
  const crumbs = crumbsFor(pathname, title);
  return (
    <nav aria-label="현재 위치" className="min-w-0 flex-1">
      <ol className="flex min-w-0 items-center gap-1 text-sm">
        <li className="hidden shrink-0 sm:block" aria-hidden="true">
          <Home className="size-4 text-muted-foreground" />
        </li>
        {crumbs.map((c, i) => {
          const last = i === crumbs.length - 1;
          return (
            <li key={`${i}-${c.label}`} className={cn("flex min-w-0 items-center gap-1", !last && "hidden md:flex")}>
              {i > 0 && (
                <ChevronRight className={cn("size-3.5 shrink-0 text-muted-foreground", last && "hidden md:block")} aria-hidden="true" />
              )}
              {last ? (
                <span aria-current="page" className="truncate font-semibold text-foreground" title={c.label}>
                  {c.label}
                </span>
              ) : c.to ? (
                <Link to={c.to} className="max-w-48 truncate text-muted-foreground hover:text-foreground hover:underline" title={c.label}>
                  {c.label}
                </Link>
              ) : (
                <span className="truncate text-muted-foreground">{c.label}</span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

const isMac = () => typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);

/** 통합 검색 자리 — 레인 3 의 GlobalSearch 가 들어오기 전까지 자료 검색 화면으로 보낸다 (로그인 전이면 로그인 창). */
export function SearchSlot() {
  const requireLogin = useRequireLogin();
  const [mac] = React.useState(isMac);
  return (
    <button
      type="button"
      onClick={() => requireLogin("/search")}
      className="inline-flex min-h-10 items-center gap-2 rounded-lg border bg-background px-3 text-sm text-muted-foreground hover:text-foreground sm:w-64"
      aria-label="제안서·자료 검색"
    >
      <Search className="size-4 shrink-0" aria-hidden="true" />
      <span className="hidden flex-1 text-left sm:inline">제안서·자료 검색</span>
      <kbd aria-hidden="true" className="hidden rounded border bg-muted px-1.5 font-sans text-xs sm:inline">
        {mac ? "⌘K" : "Ctrl K"}
      </kbd>
    </button>
  );
}

/** 위쪽 막대 — 좁은 화면 메뉴 단추, 경로 표시, 통합 검색, 작성 가이드(?) */
export function TopBar({
  onOpenMenu,
  menuOpen,
  search,
}: {
  onOpenMenu: () => void;
  menuOpen: boolean;
  /** 통합 검색 (없으면 SearchSlot) */
  search?: React.ReactNode;
}) {
  return (
    <header className="sticky top-0 z-30 border-b bg-card">
      <div className="flex h-14 items-center gap-2 px-3 sm:px-4">
        <button
          type="button"
          onClick={onOpenMenu}
          className="inline-flex size-10 shrink-0 items-center justify-center rounded-lg text-foreground hover:bg-accent lg:hidden"
          aria-label="메뉴 열기"
          aria-expanded={menuOpen}
          aria-controls="mobile-menu"
        >
          <Menu className="size-5" aria-hidden="true" />
        </button>
        <Breadcrumb />
        <div className="flex shrink-0 items-center gap-1">
          {search ?? <SearchSlot />}
          <Link
            to="/guide"
            className="inline-flex size-10 items-center justify-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground"
            aria-label="작성 가이드"
            title="작성 가이드"
          >
            <CircleHelp className="size-5" aria-hidden="true" />
          </Link>
        </div>
      </div>
    </header>
  );
}
