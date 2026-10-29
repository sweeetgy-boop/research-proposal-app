/** 연구 작업실 히어로 — 안내 문구, [새 제안서], 작성 중인 제안서가 있으면 [이어서 작성하기](가장 최근 것).
 *  만든 제안서가 0건(또는 로그인 전)이면 [새 제안서]가 가장 눈에 띈다. */
import { Link } from "react-router";
import { ArrowRight, FilePlus2 } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Eyebrow } from "./parts";

export function HomeHero({ continueTo, continueTitle }: { continueTo: string | null; continueTitle?: string }) {
  const resume = continueTo !== null;
  return (
    <section
      aria-labelledby="home-hero-title"
      className="relative overflow-hidden rounded-2xl border border-indigo-100 bg-indigo-50 px-6 py-8 sm:px-8 sm:py-10 dark:border-indigo-900/60 dark:bg-indigo-950/40"
    >
      <div className="relative z-10 max-w-xl">
        <Eyebrow>Idea to proposal</Eyebrow>
        <h1 id="home-hero-title" className="mt-3 text-3xl font-bold leading-tight tracking-tight sm:text-4xl">
          <span className="block">아이디어에서 제안서까지,</span>
          <span className="block text-primary">Research Studio에서.</span>
        </h1>
        <p className="mt-4 text-base text-muted-foreground">
          연구 아이디어를 적으면 기존 과제와 겹치는지 확인하고,
          <br className="hidden sm:inline" /> 근거를 붙인 초안을 만들어 검토·마무리까지 함께 갑니다.
        </p>
        <div className="mt-6 flex flex-wrap items-center gap-3">
          {resume && (
            <Link to={continueTo} className={cn(buttonVariants({ size: "lg" }))} title={continueTitle}>
              이어서 작성하기
              <ArrowRight aria-hidden="true" />
            </Link>
          )}
          <Link to="/new" className={cn(buttonVariants({ size: "lg", variant: resume ? "outline" : "default" }), resume && "bg-card")}>
            <FilePlus2 aria-hidden="true" />
            새 제안서
            {!resume && <ArrowRight aria-hidden="true" />}
          </Link>
        </div>
      </div>
      <HeroIllustration />
    </section>
  );
}

/** 기울어진 문서 카드(막대그래프·체크 표시)와 옅은 원형 궤도선 — 장식, 외부 파일 없음 */
function HeroIllustration() {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      viewBox="0 0 260 200"
      className="pointer-events-none absolute -right-6 top-1/2 hidden h-56 w-72 -translate-y-1/2 md:block lg:right-6"
    >
      <ellipse cx="130" cy="104" rx="104" ry="74" transform="rotate(-18 130 104)" className="fill-none stroke-indigo-300 dark:stroke-indigo-700" strokeWidth="1.2" />
      <ellipse cx="130" cy="104" rx="78" ry="56" transform="rotate(24 130 104)" className="fill-none stroke-indigo-200 dark:stroke-indigo-800" strokeWidth="1" />
      <circle cx="34" cy="120" r="3" className="fill-indigo-300 dark:fill-indigo-600" />
      <path d="M214 34 l3 8 8 3 -8 3 -3 8 -3 -8 -8 -3 8 -3z" className="fill-indigo-300 dark:fill-indigo-600" />
      <g transform="rotate(12 130 100)">
        <rect x="88" y="30" width="96" height="128" rx="10" className="fill-white stroke-indigo-100 dark:fill-slate-900 dark:stroke-indigo-900" strokeWidth="1.5" />
        <rect x="102" y="48" width="56" height="5" rx="2.5" className="fill-indigo-200 dark:fill-indigo-800" />
        <rect x="102" y="62" width="68" height="6" rx="3" className="fill-primary" />
        <rect x="102" y="76" width="62" height="4" rx="2" className="fill-indigo-100 dark:fill-indigo-900" />
        <rect x="102" y="86" width="66" height="4" rx="2" className="fill-indigo-100 dark:fill-indigo-900" />
        <rect x="102" y="96" width="48" height="4" rx="2" className="fill-indigo-100 dark:fill-indigo-900" />
        <rect x="104" y="128" width="10" height="16" rx="2" className="fill-indigo-300 dark:fill-indigo-600" />
        <rect x="120" y="120" width="10" height="24" rx="2" className="fill-indigo-400 dark:fill-indigo-500" />
        <rect x="136" y="124" width="10" height="20" rx="2" className="fill-indigo-300 dark:fill-indigo-600" />
        <rect x="152" y="112" width="10" height="32" rx="2" className="fill-primary" />
      </g>
      <circle cx="196" cy="138" r="15" className="fill-emerald-100 dark:fill-emerald-900" />
      <path d="M189 138 l5 5 9 -10" className="fill-none stroke-emerald-600 dark:stroke-emerald-300" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
