import * as React from "react";
import { Link, useNavigate } from "react-router";
import { ClipboardList, Gauge, Star } from "lucide-react";
import { useRunContext } from "./useRunContext";
import { useFeedback, useSubmitCheck, useUsage } from "@/api/hooks";
import { SubmitCheckList } from "@/features/submit/SubmitCheckList";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { useToast } from "@/components/ui/toast";
import { stepLabel } from "@/lib/sections";

function seconds(n: number | undefined): string {
  if (n === undefined || n === null) return "—";
  if (n < 60) return `${Math.round(n)}초`;
  return `${Math.floor(n / 60)}분 ${Math.round(n % 60)}초`;
}

export default function SubmitCheck() {
  const { run } = useRunContext();
  const id = run.run_id;
  const navigate = useNavigate();
  const { toast } = useToast();
  const check = useSubmitCheck(id);
  const usage = useUsage(id);
  const feedback = useFeedback(id);
  const [score, setScore] = React.useState<number | null>(null);
  const [comment, setComment] = React.useState("");
  const u = usage.data?.usage ?? null;
  const finalized = run.status === "finalized";

  const sendFeedback = async (e: React.FormEvent) => {
    e.preventDefault();
    if (score === null) return;
    try {
      await feedback.mutateAsync({ score, comment });
      toast("만족도를 기록했습니다. 고맙습니다.", "success");
    } catch {
      /* banner */
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="min-w-0 space-y-4">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <ClipboardList className="size-5" aria-hidden="true" />
            제출 전 점검
          </h2>
          <p className="text-sm text-muted-foreground">필수 섹션·미해결 알림·근거 승인·남은 메모·최종 검토 이후 수정·선택형 확정·칸 길이·전략 목록·검토 상태를 한 장으로 봅니다. 항목을 누르면 그 자리로 갑니다. 마무리를 막지는 않습니다.</p>
        </div>
        {check.isPending ? (
          <SkeletonBlock lines={9} />
        ) : check.error ? (
          <ProblemBanner error={check.error} onRetry={() => check.refetch()} />
        ) : check.data === null ? (
          <Alert variant="info">
            <ClipboardList aria-hidden="true" />
            <div>
              <AlertTitle>제출 전 점검이 꺼져 있습니다</AlertTitle>
              <AlertDescription>usability.yaml submit_check 를 켜면 보입니다. 최종 마무리로 바로 갈 수 있습니다.</AlertDescription>
            </div>
          </Alert>
        ) : check.data ? (
          <>
            <p className="flex flex-wrap items-center gap-2 text-sm" role="status">
              {check.data.ok ? <Badge variant="success">모두 통과</Badge> : <Badge variant="destructive">확인 필요 {check.data.failing}건</Badge>}
              <Button variant="ghost" size="sm" onClick={() => check.refetch()}>
                다시 점검
              </Button>
            </p>
            <SubmitCheckList check={check.data} runId={id} onGo={(p) => navigate(p)} />
          </>
        ) : null}
        <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-4">
          <Link to={`/runs/${id}/final-review`} className={buttonVariants({ variant: "outline" })}>
            ← 최종 검토
          </Link>
          <Link to={`/runs/${id}/finalize`} className={buttonVariants()}>
            최종 마무리 →
          </Link>
        </div>
      </div>

      <aside className="min-w-0 space-y-6">
        <section aria-labelledby="usage-h" className="rounded-lg border p-3">
          <h2 id="usage-h" className="mb-2 flex items-center gap-2 text-base font-semibold">
            <Gauge className="size-4" aria-hidden="true" />
            사용 기록
          </h2>
          {usage.isPending ? (
            <SkeletonBlock lines={4} />
          ) : !u ? (
            <p className="text-sm text-muted-foreground">기록이 없습니다 (usage_record 꺼짐 또는 아직 없음).</p>
          ) : (
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
              <dt className="text-muted-foreground">총 시간</dt>
              <dd>{seconds(u.total_seconds)}</dd>
              {Object.entries(u.step_seconds).map(([k, v]) => (
                <React.Fragment key={k}>
                  <dt className="pl-2 text-muted-foreground">· {stepLabel(k)}</dt>
                  <dd>{seconds(v)}</dd>
                </React.Fragment>
              ))}
              <dt className="text-muted-foreground">근거 판단</dt>
              <dd>
                승인 {u.evidence.approve} · 교체 {u.evidence.replace} · 제외 {u.evidence.exclude} / {u.evidence.total}
                {u.evidence.total > 0 && ` (승인 ${Math.round((u.evidence.ratios.approve ?? 0) * 100)}%)`}
              </dd>
              <dt className="text-muted-foreground">AI 다시 쓰기</dt>
              <dd>{u.rewrites}회</dd>
              <dt className="text-muted-foreground">체크리스트 충족</dt>
              <dd>{u.checklist_coverage === null ? "—" : `${Math.round(u.checklist_coverage * 100)}%`}</dd>
              <dt className="text-muted-foreground">HWPX</dt>
              <dd>{u.hwpx_success === null ? "아직" : u.hwpx_success ? "성공" : "실패"}</dd>
              <dt className="text-muted-foreground">만족도</dt>
              <dd>{u.satisfaction ? `${u.satisfaction.score}/5${u.satisfaction.comment ? ` — ${u.satisfaction.comment}` : ""}` : "미기록"}</dd>
            </dl>
          )}
        </section>

        <section aria-labelledby="fb-h" className="rounded-lg border p-3">
          <h2 id="fb-h" className="mb-2 flex items-center gap-2 text-base font-semibold">
            <Star className="size-4" aria-hidden="true" />
            만족도
          </h2>
          {!finalized ? (
            <p className="text-sm text-muted-foreground">최종 마무리(HWPX 내려받기) 뒤에 기록할 수 있습니다.</p>
          ) : u?.satisfaction ? (
            <p className="text-sm" role="status">
              기록됨: {u.satisfaction.score}/5{u.satisfaction.comment ? ` — ${u.satisfaction.comment}` : ""}
            </p>
          ) : (
            <form onSubmit={sendFeedback} className="space-y-3">
              <fieldset>
                <legend className="text-sm">이 앱이 제안서 작성에 얼마나 도움이 되었습니까? (1 전혀 ~ 5 매우)</legend>
                <div role="radiogroup" aria-label="만족도 점수" className="mt-1 flex gap-2">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <Label key={n} className="flex items-center gap-1 font-normal">
                      <input type="radio" name="score" value={n} checked={score === n} onChange={() => setScore(n)} className="size-4 accent-primary" />
                      {n}
                    </Label>
                  ))}
                </div>
              </fieldset>
              <div className="space-y-1">
                <Label htmlFor="fb-comment">한 줄 소감 (선택, 200자, 이메일·전화번호 금지)</Label>
                <Input id="fb-comment" value={comment} maxLength={200} onChange={(e) => setComment(e.target.value)} />
              </div>
              <ProblemBanner error={feedback.error} />
              <Button type="submit" disabled={score === null || feedback.isPending}>
                {feedback.isPending ? "기록 중…" : "만족도 보내기"}
              </Button>
            </form>
          )}
        </section>
      </aside>
    </div>
  );
}
