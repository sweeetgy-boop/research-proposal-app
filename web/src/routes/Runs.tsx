import { Link } from "react-router";
import { FilePlus2, ListOrdered } from "lucide-react";
import { useRuns } from "@/api/hooks";
import { useSessionLabel } from "@/auth/useSession";
import { buttonVariants } from "@/components/ui/button";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { EmptyState } from "@/components/EmptyState";
import { RunTable } from "@/features/home/RunTable";

/** 내 제안서 — 홈 "최근 제안서"와 같은 줄 모양(탭·제목 검색·정렬), 전부 보이고 작성 번호(오류 보고용)를 함께 둔다. */
export default function Runs() {
  const q = useRuns();
  const guest = useSessionLabel() === "공용 계정";
  const newButton = (
    <Link to="/new" className={buttonVariants()}>
      <FilePlus2 aria-hidden="true" />
      새 제안서
    </Link>
  );
  const plainHead = (
    <div className="flex flex-wrap items-end justify-between gap-2">
      <h1 className="text-2xl font-bold tracking-tight">내 제안서</h1>
      {newButton}
    </div>
  );
  return (
    <div className="space-y-4">
      {(q.isPending || q.error) && plainHead}
      {q.isPending && <SkeletonBlock lines={5} />}
      <ProblemBanner error={q.error} onRetry={() => q.refetch()} />
      {q.data && q.data.runs.length === 0 && (
        <>
          {plainHead}
          <EmptyState icon={ListOrdered} title="아직 만든 제안서가 없습니다" description="새 제안서에서 아이디어를 입력하면 여기에 쌓입니다." />
        </>
      )}
      {q.data && q.data.runs.length > 0 && (
        <RunTable runs={q.data.runs} title="내 제안서" headingLevel="h1" showRunId guest={guest} actions={newButton} />
      )}
    </div>
  );
}
