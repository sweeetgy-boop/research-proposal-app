import { CircleHelp, Database, FilePlus2, FolderOpen, LayoutGrid, LogIn, LogOut, UserRound } from "lucide-react";
import { NavLink, useLocation } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { listRuns } from "@/api/endpoints";
import { keys } from "@/api/hooks";
import { useLoggedIn, useSessionLabel } from "@/auth/useSession";
import { useLoginDialog } from "@/features/auth/loginContext";
import { ThemeToggle } from "@/components/ThemeToggle";
import { cn } from "@/lib/utils";
import { APP_NAME } from "./crumbs";

const GUEST_LABEL = "공용 계정";

interface NavItem {
  to: string;
  label: string;
  icon: typeof LayoutGrid;
  /** 이 주소로 시작하면 선택된 것으로 본다 */
  match: (pathname: string) => boolean;
  count?: boolean;
}

const SIDEBAR_NAV: NavItem[] = [
  { to: "/", label: "연구 작업실", icon: LayoutGrid, match: (p) => p === "/" },
  { to: "/new", label: "새 제안서", icon: FilePlus2, match: (p) => p === "/new" || p.startsWith("/new/") },
  { to: "/runs", label: "내 제안서", icon: FolderOpen, match: (p) => p === "/runs" || p.startsWith("/runs/"), count: true },
];

/** 내 제안서 건수 — 로그인 뒤에만 부른다 (로그인 전에는 API 를 부르지 않는다). 내 제안서 화면과 같은 캐시 키. */
function useRunCount(enabled: boolean): number | null {
  const q = useQuery({ queryKey: keys.runs, queryFn: () => listRuns(50), enabled });
  return enabled && q.data ? q.data.runs.length : null;
}

function itemClass(active: boolean) {
  return cn(
    "flex min-h-10 items-center gap-2.5 rounded-lg px-3 text-sm font-medium transition-colors",
    active ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-accent hover:text-foreground",
  );
}

/** 왼쪽 사이드바 내용 — 넓은 화면은 고정 열, 좁은 화면은 접는 메뉴(MobileMenu) 안에서 같은 것을 그린다.
 *  onNavigate: 메뉴를 누르면 부른다 (접는 메뉴 닫기). */
export function Sidebar({ onNavigate, navLabel = "주 메뉴" }: { onNavigate?: () => void; navLabel?: string }) {
  const { pathname } = useLocation();
  const loggedIn = useLoggedIn();
  const label = useSessionLabel();
  const dialog = useLoginDialog();
  const count = useRunCount(loggedIn);
  const isGuest = label === GUEST_LABEL;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <NavLink to="/" onClick={onNavigate} className="flex items-center gap-2.5 px-4 pb-4 pt-5" aria-label={`${APP_NAME} — 연구 작업실로`}>
        <span
          aria-hidden="true"
          className="grid size-9 shrink-0 place-items-center rounded-xl bg-primary text-lg font-bold text-primary-foreground"
        >
          R
        </span>
        <span className="text-base font-bold leading-tight tracking-tight">{APP_NAME}</span>
      </NavLink>

      <nav aria-label={navLabel} className="min-h-0 flex-1 overflow-y-auto px-2">
        <p aria-hidden="true" className="px-3 pb-2 pt-3 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          Workspace
        </p>
        <ul className="space-y-1">
          {SIDEBAR_NAV.map(({ to, label: text, icon: Icon, match, count: withCount }) => {
            const active = match(pathname);
            return (
              <li key={to}>
                <NavLink to={to} end onClick={onNavigate} className={itemClass(active)} aria-current={active ? "page" : undefined}>
                  <Icon className="size-4 shrink-0" aria-hidden="true" />
                  <span className="flex-1">{text}</span>
                  {withCount && count !== null && (
                    <span className="text-xs tabular-nums" aria-label={`${count}건`}>
                      {count}
                    </span>
                  )}
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="space-y-1 px-2 pb-2">
        <NavLink to="/guide" onClick={onNavigate} className={itemClass(pathname === "/guide")} aria-current={pathname === "/guide" ? "page" : undefined}>
          <CircleHelp className="size-4 shrink-0" aria-hidden="true" />
          작성 가이드
        </NavLink>
        <NavLink
          to="/sources"
          onClick={onNavigate}
          className={cn(itemClass(pathname === "/sources"), "min-h-9 text-xs")}
          aria-current={pathname === "/sources" ? "page" : undefined}
        >
          <Database className="size-3.5 shrink-0" aria-hidden="true" />
          자료 현황
        </NavLink>
      </div>

      <div className="mx-2 mb-2 rounded-xl border bg-muted/50 p-3 text-xs leading-relaxed text-muted-foreground">
        <p>제안서는 연구원 서버에 저장됩니다.</p>
        {isGuest && <p className="mt-1 font-medium text-foreground">공용 계정의 제안서는 함께 쓰는 사람에게 보입니다.</p>}
      </div>

      <div
        className="flex items-center gap-2 border-t px-3 py-3"
        role="group"
        aria-label={loggedIn ? `로그인 종류: ${label ?? "로그인됨"}` : "로그인 전"}
      >
        <span aria-hidden="true" className="grid size-9 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
          <UserRound className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          {loggedIn ? (
            <>
              <p className="truncate text-sm font-semibold">
                {label ?? "로그인됨"}
              </p>
              <button
                type="button"
                onClick={() => {
                  onNavigate?.();
                  void dialog?.logoutTo("/");
                }}
                className="inline-flex min-h-6 items-center gap-1 text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
              >
                <LogOut className="size-3.5" aria-hidden="true" />
                로그아웃
              </button>
            </>
          ) : (
            <>
              <p className="text-sm font-semibold">로그인 전</p>
              <button
                type="button"
                onClick={() => {
                  onNavigate?.();
                  dialog?.open();
                }}
                className="inline-flex min-h-6 items-center gap-1 text-xs font-medium text-primary underline-offset-2 hover:underline"
              >
                <LogIn className="size-3.5" aria-hidden="true" />
                로그인
              </button>
            </>
          )}
        </div>
        <ThemeToggle />
      </div>
    </div>
  );
}
