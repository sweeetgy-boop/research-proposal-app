/** 홈 오른쪽 열 — "연구 한눈에 보기"(로그인한 계정 기준 건수)와 작성 팁 카드. */
import { Link } from "react-router";
import { ArrowRight, CircleCheck, Clock3, FileText, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Eyebrow } from "@/components/ui/eyebrow";
import type { RunCounts } from "./runView";

const ROWS: { key: keyof RunCounts; title: string; hint: string; icon: LucideIcon; tile: string }[] = [
  {
    key: "all",
    title: "전체 제안서",
    hint: "이 계정으로 만든 제안서",
    icon: FileText,
    tile: "bg-primary-soft text-primary-soft-foreground",
  },
  {
    key: "writing",
    title: "작성 중",
    hint: "최종 마무리 전",
    icon: Clock3,
    tile: "bg-apricot text-apricot-foreground",
  },
  {
    key: "done",
    title: "마무리 완료",
    hint: "양식 파일을 받을 수 있음",
    icon: CircleCheck,
    tile: "bg-mint text-mint-foreground",
  },
];

export function OverviewCard({ counts, loading }: { counts: RunCounts | null; loading?: boolean }) {
  return (
    <section aria-labelledby="overview-title" className="rounded-xl border bg-card shadow-card p-5" aria-busy={loading || undefined}>
      <div className="flex items-baseline justify-between gap-2">
        <h2 id="overview-title" className="text-base font-bold">
          연구 한눈에 보기
        </h2>
        <Eyebrow className="text-muted-foreground">Overview</Eyebrow>
      </div>
      <ul className="mt-4 space-y-4">
        {ROWS.map(({ key, title, hint, icon: Icon, tile }) => (
          <li key={key} className="flex items-center gap-3" data-testid={`overview-${key}`}>
            <span className={cn("grid size-10 shrink-0 place-items-center rounded-xl", tile)}>
              <Icon className="size-5" aria-hidden="true" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-semibold">{title}</span>
              <span className="block text-xs text-muted-foreground">{hint}</span>
            </span>
            <span className="shrink-0 whitespace-nowrap">
              <span className="text-2xl font-bold tabular-nums">{counts ? counts[key] : "–"}</span>
              <span className="ml-1 text-sm text-muted-foreground">편</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function TipCard() {
  return (
    <section
      aria-labelledby="tip-title"
      className="rounded-xl bg-mint p-5"
    >
      <Eyebrow className="text-mint-foreground">Writing tip</Eyebrow>
      <h2 id="tip-title" className="mt-2 text-base font-bold leading-snug">
        <span className="block">현재 상황과 한계를</span>
        <span className="block">구체적으로 적어 보세요.</span>
      </h2>
      <p className="mt-2 text-sm text-muted-foreground">
        ① 입력의 네 칸(현재 상황·문제, 발생 원인, 현행 대응의 한계, 해결 목표)이 분명할수록 유사과제 확인과 초안이 그 내용에 맞춰집니다.
      </p>
      <Link
        to="/guide"
        className="mt-3 inline-flex min-h-10 items-center gap-1 text-sm font-semibold text-link-green underline-offset-4 hover:underline"
      >
        작성 가이드에서 사용 순서 보기
        <ArrowRight className="size-4" aria-hidden="true" />
      </Link>
    </section>
  );
}
