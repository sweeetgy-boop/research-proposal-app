import { Database, FilePlus2, ListOrdered, LogOut, Search } from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "./ThemeToggle";
import { Stepper } from "./Stepper";
import { useLoggedIn } from "@/auth/useSession";
import { logout } from "@/api/endpoints";
import { cn } from "@/lib/utils";

function stepFromPath(pathname: string): number | null {
  if (pathname === "/new") return 1;
  if (pathname === "/new/precheck" || pathname === "/new/brief") return 2;
  if (pathname === "/new/clarify") return 3;
  const m = /^\/runs\/[^/]+(?:\/([a-z-]+))?$/.exec(pathname);
  if (!m) return null;
  switch (m[1]) {
    case undefined:
    case "draft":
      return 3;
    case "edit":
    case "versions":
      return 4;
    case "final-review":
    case "submit-check":
      return 5;
    case "finalize":
      return 6;
    default:
      return null;
  }
}

const NAV = [
  { to: "/new", label: "새 제안서", icon: FilePlus2 },
  { to: "/runs", label: "run 목록", icon: ListOrdered },
  { to: "/search", label: "자료 검색", icon: Search },
  { to: "/sources", label: "자료원 상태", icon: Database },
];

export function Layout() {
  const loggedIn = useLoggedIn();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const step = stepFromPath(pathname);

  const onLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="flex min-h-dvh flex-col">
      <a href="#main" className="skip-link">
        본문으로 건너뛰기
      </a>
      <header className="border-b bg-card">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
          <NavLink to="/new" className="text-base font-bold tracking-tight sm:text-lg">
            연구과제 제안서 작성 보조
          </NavLink>
          <nav aria-label="주 메뉴" className="relative order-3 -mx-1 flex w-full min-w-0 gap-1 overflow-x-auto sm:order-2 sm:ml-auto sm:w-auto">
            {loggedIn &&
              NAV.map(({ to, label, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    cn(
                      "inline-flex min-h-10 items-center gap-1.5 whitespace-nowrap rounded-md px-2.5 text-sm font-medium",
                      isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent hover:text-foreground",
                    )
                  }
                >
                  <Icon className="size-4" aria-hidden="true" />
                  {label}
                </NavLink>
              ))}
          </nav>
          <div className="order-2 ml-auto flex items-center gap-1 sm:order-3 sm:ml-0">
            <ThemeToggle />
            {loggedIn && (
              <Button variant="ghost" size="sm" onClick={onLogout} aria-label="로그아웃">
                <LogOut aria-hidden="true" />
                <span className="hidden sm:inline">로그아웃</span>
              </Button>
            )}
          </div>
        </div>
        {loggedIn && step !== null && (
          <div className="mx-auto max-w-6xl px-4 pb-3">
            <Stepper current={step} />
          </div>
        )}
      </header>
      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <Outlet />
      </main>
      <footer className="border-t py-4 text-center text-xs text-muted-foreground">
        초안·검토 의견·검색 결과는 수집 자료와 모델 출력으로, 제안자가 확인한 뒤에만 사용합니다.
      </footer>
    </div>
  );
}
