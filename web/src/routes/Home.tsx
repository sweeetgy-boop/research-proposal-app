/** 연구 작업실(홈, "/") — 히어로·연구 한눈에 보기·작성 팁·최근 제안서·시작 안내. 모두 실제 데이터.
 *  로그인 전에는 히어로와 시작 안내만 보이고, "연구 한눈에 보기" 자리에 로그인 카드가 온다 — 개인 데이터와
 *  세션이 필요한 API 는 부르지 않는다. 로그인하면 같은 자리에서 건수와 표가 채워진다. */
import type { ReactNode } from "react";
import { useRuns } from "@/api/hooks";
import { useLoggedIn, useSessionLabel } from "@/auth/useSession";
import { ProblemBanner } from "@/components/ProblemBanner";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { HomeHero } from "@/features/home/HomeHero";
import { LoginSlot } from "@/features/home/LoginSlot";
import { RunTable } from "@/features/home/RunTable";
import { OverviewCard, TipCard } from "@/features/home/SideCards";
import { StartGuide } from "@/features/home/StartGuide";
import { continuePath, displayTitle, latestInProgress, runCounts } from "@/features/home/runView";

export default function Home() {
  const loggedIn = useLoggedIn();
  return loggedIn ? <HomeSignedIn /> : <HomeSignedOut />;
}

function Grid({ hero, side, children }: { hero: ReactNode; side: ReactNode; children?: ReactNode }) {
  return (
    <div className="space-y-6">
      {/* 넓은 화면: 왼쪽 히어로·표, 오른쪽 열. 좁은 화면: 히어로 → 한눈에 보기 → 표 순서 */}
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0 lg:col-start-1 lg:row-start-1">{hero}</div>
        <div className="space-y-6 lg:col-start-2 lg:row-span-2 lg:row-start-1">{side}</div>
        {children && <div className="min-w-0 space-y-6 lg:col-start-1 lg:row-start-2">{children}</div>}
      </div>
      <StartGuide />
    </div>
  );
}

function HomeSignedOut() {
  return <Grid hero={<HomeHero continueTo={null} />} side={<LoginSlot />} />;
}

function HomeSignedIn() {
  const q = useRuns();
  const guest = useSessionLabel() === "공용 계정";
  const runs = q.data?.runs ?? [];
  const latest = latestInProgress(runs);
  return (
    <Grid
      hero={<HomeHero continueTo={latest ? continuePath(latest) : null} continueTitle={latest ? displayTitle(latest) : undefined} />}
      side={
        <>
          <OverviewCard counts={q.data ? runCounts(runs) : null} loading={q.isPending} />
          <TipCard />
        </>
      }
    >
      <ProblemBanner error={q.error} onRetry={() => q.refetch()} />
      {q.isPending && (
        <div className="rounded-2xl border bg-card p-5">
          <SkeletonBlock lines={4} />
        </div>
      )}
      {q.data && <RunTable runs={runs} title="최근 제안서" limit={5} showAllLink guest={guest} />}
    </Grid>
  );
}
