import { Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ProblemBanner } from "@/components/ProblemBanner";
import { UntrustedText } from "@/components/UntrustedText";
import { sectionTitle } from "@/lib/sections";
import { useSectionsProgress } from "@/features/figures/figureJob";

/** ③ 생성 중 — 다 쓴 섹션부터 먼저 보인다(읽기 전용, ADR 0045). 섹션은 동시에 쓰이므로 끝나는 차례가
 *  양식 차례와 다를 수 있다. 아직 쓰는 섹션은 "작성 중". 버전이 아니다 — 마무리 정리 전 글이다. */
export function SectionsSoFar({ runId, generating }: { runId: string; generating: boolean }) {
  const q = useSectionsProgress(runId, generating);
  if (!generating) return null;
  const data = q.data;
  const done = data?.sections ?? [];
  const pending = data?.pending ?? [];
  return (
    <section aria-labelledby="so-far-h" className="space-y-3">
      <h3 id="so-far-h" className="text-base font-semibold">
        먼저 보기 — 다 쓴 섹션 {done.length}개{pending.length ? ` · 작성 중 ${pending.length}개` : ""}
      </h3>
      <p className="text-xs text-muted-foreground">읽기만 할 수 있습니다. 모든 섹션을 다 쓰고 규칙 검사를 마치면 초안 보기로 넘어가 고칠 수 있습니다.</p>
      <ProblemBanner error={q.error} />
      {done.length === 0 && !q.error && <p className="text-sm text-muted-foreground">아직 다 쓴 섹션이 없습니다.</p>}
      <ol className="space-y-3">
        {done.map((s) => (
          <li key={s.key} className="rounded-lg border p-3" data-testid="section-so-far">
            <h4 className="flex flex-wrap items-center gap-2 text-sm font-semibold">
              {sectionTitle(s.key)}
              <Badge variant="success">작성됨</Badge>
            </h4>
            {s.sentences.length === 0 ? (
              <p className="mt-1 text-sm text-muted-foreground">(본문 없이 체크 칸으로만 들어가거나 근거가 부족해 빈칸입니다)</p>
            ) : (
              <ul className="mt-1 space-y-1 text-sm">
                {s.sentences.map((t, i) => (
                  <li key={i}>
                    <UntrustedText text={t} />
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
        {pending.map((key) => (
          <li key={key} className="flex items-center gap-2 rounded-lg border border-dashed p-3 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            <span className="font-medium text-foreground">{sectionTitle(key)}</span>
            <span>작성 중</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
