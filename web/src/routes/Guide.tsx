/** 작성 가이드 (/guide) — 시범 안내서의 사용자용 부분을 화면 글로. 로그인 없이도 열린다(개인 데이터 없음). */
import { Link } from "react-router";
import { FilePlus2 } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { GUIDE_SECTIONS } from "@/features/guide/content";
import { Eyebrow } from "@/features/home/parts";

export default function Guide() {
  return (
    <div className="space-y-6">
      <header className="rounded-2xl border border-indigo-100 bg-indigo-50 px-6 py-7 dark:border-indigo-900/60 dark:bg-indigo-950/40">
        <Eyebrow>Guide</Eyebrow>
        <h1 className="mt-2 text-2xl font-bold tracking-tight sm:text-3xl">작성 가이드</h1>
        <p className="mt-2 max-w-2xl text-muted-foreground">
          Research Studio로 제안서를 쓰는 순서와 알아 둘 점입니다. 제안서는 연구원 서버에 저장됩니다.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Link to="/new" className={buttonVariants()}>
            <FilePlus2 aria-hidden="true" />새 제안서
          </Link>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[13rem_minmax(0,1fr)]">
        <nav aria-label="작성 가이드 목차" className="lg:sticky lg:top-4 lg:self-start">
          <ol className="flex flex-wrap gap-2 lg:flex-col lg:gap-1">
            {GUIDE_SECTIONS.map((s, i) => (
              <li key={s.id}>
                <a
                  href={`#${s.id}`}
                  className="inline-flex min-h-10 items-center rounded-lg px-3 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
                >
                  {i + 1}. {s.title}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        <div className="min-w-0 space-y-6">
          {GUIDE_SECTIONS.map((s) => {
            const List = s.ordered ? "ol" : "ul";
            return (
              <section key={s.id} id={s.id} aria-labelledby={`${s.id}-title`} className="scroll-mt-4 rounded-2xl border bg-card p-5 sm:p-6">
                <Eyebrow>{s.eyebrow}</Eyebrow>
                <h2 id={`${s.id}-title`} className="mt-1 text-xl font-bold">
                  {s.title}
                </h2>
                {s.intro && <div className="mt-3 space-y-3 text-sm leading-relaxed text-muted-foreground">{s.intro}</div>}
                <List className={s.ordered ? "mt-4 space-y-4" : "mt-4 list-disc space-y-2 pl-5 text-sm leading-relaxed text-muted-foreground"}>
                  {s.items.map((it, i) =>
                    s.ordered ? (
                      <li key={i} className="flex gap-3">
                        <span
                          aria-hidden="true"
                          className="grid h-8 min-w-8 shrink-0 place-items-center rounded-lg bg-indigo-50 px-1.5 text-sm font-semibold tabular-nums text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-200"
                        >
                          {String(i + 1).padStart(2, "0")}
                        </span>
                        <div className="min-w-0 text-sm leading-relaxed text-muted-foreground">
                          {it.title && <h3 className="text-base font-semibold text-foreground">{it.title}</h3>}
                          <p className={it.title ? "mt-1" : undefined}>{it.body}</p>
                          {it.sub && (
                            <ul className="mt-2 list-disc space-y-1.5 pl-5">
                              {it.sub.map((x, j) => (
                                <li key={j}>{x}</li>
                              ))}
                            </ul>
                          )}
                        </div>
                      </li>
                    ) : (
                      <li key={i}>{it.body}</li>
                    ),
                  )}
                </List>
              </section>
            );
          })}
        </div>
      </div>
    </div>
  );
}
