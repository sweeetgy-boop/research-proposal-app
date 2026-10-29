import * as React from "react";
import { Outlet, useLocation } from "react-router";
import { Stepper } from "./Stepper";
import { Sidebar } from "./frame/Sidebar";
import { TopBar } from "./frame/TopBar";
import { MobileMenu } from "./frame/MobileMenu";
import { useLoggedIn } from "@/auth/useSession";
import { LoginDialogProvider } from "@/features/auth/LoginDialog";
import { useDeployVersion } from "@/api/hooks";
import { formatDeployedAt } from "@/lib/deployVersion";
import { runStepFromSub } from "@/lib/runSteps";
import { GlobalSearch } from "@/features/globalsearch/GlobalSearch";

/** 경로 → 흐름 단계. run 안(/runs/:id/…)은 RunLayout 이 run 상태를 알고 단계 링크를 그리므로
 *  머리의 단계 표시는 /new… 에서만 쓴다 (runInPath). */
function stepFromPath(pathname: string): number | null {
  if (pathname === "/new") return 1;
  if (pathname === "/new/precheck" || pathname === "/new/brief") return 2;
  if (pathname === "/new/clarify") return 3;
  const m = /^\/runs\/[^/]+(?:\/([a-z-]+))?$/.exec(pathname);
  if (!m) return null;
  return runStepFromSub(m[1]);
}

const runInPath = (pathname: string) => /^\/runs\/[^/]+/.test(pathname);

export function Layout() {
  return (
    <LoginDialogProvider>
      <Frame />
    </LoginDialogProvider>
  );
}

/** 화면 틀 — 왼쪽 사이드바(넓은 화면 고정, 좁은 화면은 접는 메뉴) + 위쪽 막대(경로·통합 검색) + 본문.
 *  아래 이동 막대(StepNavBar)는 사이드바 오른쪽에 붙고 높이(--stepnav-h)만큼 본문을 띄운다. */
function Frame() {
  const loggedIn = useLoggedIn();
  const version = useDeployVersion().data?.version;
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = React.useState(false);
  const closeMenu = React.useCallback(() => setMenuOpen(false), []);
  const step = stepFromPath(pathname);

  return (
    <div className="min-h-dvh bg-background">
      <a href="#main" className="skip-link">
        본문으로 건너뛰기
      </a>
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-52 border-r bg-card lg:block" aria-label="사이드바">
        <Sidebar />
      </aside>
      <MobileMenu open={menuOpen} onClose={closeMenu} />
      <div className="flex min-h-dvh flex-col pb-[var(--stepnav-h)] lg:pl-52">
        <TopBar onOpenMenu={() => setMenuOpen(true)} menuOpen={menuOpen} search={<GlobalSearch className="min-w-0 flex-1 sm:flex-none" />} />
        {loggedIn && step !== null && !runInPath(pathname) && (
          <div className="mx-auto w-full max-w-6xl px-4 pt-4">
            <Stepper current={step} />
          </div>
        )}
        <main id="main" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
          <Outlet />
        </main>
        <footer className="border-t py-4 text-center text-xs text-muted-foreground">
          <p>초안·검토 의견·검색 결과는 수집 자료와 모델 출력으로, 제안자가 확인한 뒤에만 사용합니다.</p>
          {version?.short && (
            <p className="mt-1 font-mono" data-testid="deploy-version" aria-label="배포 버전">
              버전 {version.short} · 배포 {formatDeployedAt(version.deployed_at)}
            </p>
          )}
        </footer>
      </div>
    </div>
  );
}
