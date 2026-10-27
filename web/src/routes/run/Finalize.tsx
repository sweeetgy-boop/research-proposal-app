import * as React from "react";
import { Download, FileCheck2, RotateCcw } from "lucide-react";
import { useRunContext } from "./useRunContext";
import { useDraft, useFinalize, useRenderCheck, useReopen } from "@/api/hooks";
import type { FinalizeIn } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Select } from "@/components/ui/select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { UntrustedText } from "@/components/UntrustedText";
import { useToast } from "@/components/ui/toast";
import { sectionTitle } from "@/lib/sections";

function canFinalize(run: ReturnType<typeof useRunContext>["run"]): { ok: boolean; reason: string | null } {
  const f = run.flow;
  if (run.legacy) return { ok: false, reason: "옛 run 은 마무리할 수 없습니다." };
  if (f.has_working) return { ok: false, reason: "저장하지 않은 임시 편집이 있습니다. 직접 수정에서 저장하거나 버리십시오." };
  if (run.status === "final_reviewed" || run.status === "finalized") return { ok: true, reason: null };
  if ((run.status === "drafted" || run.status === "editing") && (f.draft_review_skipped === "no_review_llm" || f.final_reviews > 0))
    return { ok: true, reason: null };
  if (run.status === "drafted" || run.status === "editing") return { ok: false, reason: "최종 검토를 한 번 받은 뒤에 마무리할 수 있습니다 (검토 모델 키가 없으면 바로 가능)." };
  return { ok: false, reason: "생성·검토가 끝난 뒤에 마무리할 수 있습니다." };
}

export default function Finalize() {
  const { run, refetch } = useRunContext();
  const id = run.run_id;
  const draft = useDraft(id);
  const check = useRenderCheck(id);
  const finalize = useFinalize(id);
  const reopen = useReopen(id);
  const { toast } = useToast();
  const gate = canFinalize(run);

  const choiceSections = (draft.data?.sections ?? []).filter((s) => s.choices);
  const [taskType, setTaskType] = React.useState<string>("");
  const [utilization, setUtilization] = React.useState<string[]>([]);
  const [strategy, setStrategy] = React.useState<string[]>([]);
  const [version, setVersion] = React.useState<number | "">("");
  // 제안자 정보 — 이 화면의 메모리에만, 마무리 요청 본문으로만 보낸다 (저장 금지)
  const [proposer, setProposer] = React.useState({ department: "", proposed_on: "", p_rank: "", p_name: "", p_phone: "", h_rank: "", h_name: "", h_phone: "" });
  const [lastCheck, setLastCheck] = React.useState<{ count: number; version: string | null } | null>(null);

  // 제안값(또는 확정값)을 초기 선택으로
  React.useEffect(() => {
    if (!draft.data) return;
    for (const s of draft.data.sections) {
      if (!s.choices) continue;
      const ids = (s.choices.confirmed ?? s.choices.proposed).map((c) => c.id);
      if (s.key === "task_type") setTaskType((v) => v || ids[0] || "");
      if (s.key === "utilization") setUtilization((v) => (v.length ? v : ids));
      if (s.key === "strategy_alignment") setStrategy((v) => (v.length ? v : ids));
    }
  }, [draft.data]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const body: FinalizeIn = {
      task_type: taskType || null,
      utilization: utilization.length ? utilization : null,
      strategy: strategy.length ? strategy : null,
      department: proposer.department,
      proposed_on: proposer.proposed_on,
      proposer: { rank: proposer.p_rank, name: proposer.p_name, phone: proposer.p_phone },
      head: { rank: proposer.h_rank, name: proposer.h_name, phone: proposer.h_phone },
      version: version === "" ? null : version,
    };
    try {
      const out = await finalize.mutateAsync(body);
      const url = URL.createObjectURL(out.blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = out.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
      setLastCheck({ count: out.check?.count ?? 0, version: out.version });
      toast(`${out.filename} 을 내려받았습니다.`, "success");
      refetch();
      check.refetch();
    } catch {
      /* banner */
    }
  };

  const set = (k: keyof typeof proposer) => (e: React.ChangeEvent<HTMLInputElement>) => setProposer((p) => ({ ...p, [k]: e.target.value }));

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <form onSubmit={submit} className="min-w-0 space-y-6">
        <div>
          <h2 className="text-lg font-semibold">⑥ 최종 마무리 및 다운로드</h2>
          <p className="text-sm text-muted-foreground">선택형 칸을 확정하고 제안자 정보를 넣어 HWPX 양식을 받습니다. 제안자 정보는 파일에만 들어가고 서버에 저장되지 않습니다.</p>
        </div>

        {!gate.ok && (
          <Alert variant="warning" role="status">
            <FileCheck2 aria-hidden="true" />
            <div>
              <AlertTitle>아직 마무리할 수 없습니다</AlertTitle>
              <AlertDescription>{gate.reason}</AlertDescription>
            </div>
          </Alert>
        )}
        {run.flow.stale && (
          <Alert variant="warning" role="status">
            <FileCheck2 aria-hidden="true" />
            <div>
              <AlertTitle>최종 검토 이후 수정 {run.flow.stale_edits}건</AlertTitle>
              <AlertDescription>검토받지 않은 수정이 들어간 채로 마무리됩니다. 원하면 최종 검토를 다시 받으십시오.</AlertDescription>
            </div>
          </Alert>
        )}
        {run.status === "finalized" && (
          <Alert variant="success" role="status">
            <FileCheck2 aria-hidden="true" />
            <div className="flex-1">
              <AlertTitle>마무리됨</AlertTitle>
              <AlertDescription>다시 내려받을 수 있고, 수정하려면 다시 열어야 합니다.</AlertDescription>
              <Button type="button" variant="outline" size="sm" className="mt-2" onClick={() => reopen.mutate(undefined, { onSuccess: () => toast("다시 열었습니다 (수정 중).") })} disabled={reopen.isPending}>
                <RotateCcw aria-hidden="true" />
                다시 열기 (수정 중으로)
              </Button>
              <ProblemBanner error={reopen.error} className="mt-2" />
            </div>
          </Alert>
        )}

        <fieldset className="space-y-4 rounded-lg border p-4" disabled={!gate.ok}>
          <legend className="px-1 font-semibold">선택형 확정 (체크 칸)</legend>
          {draft.isPending && <SkeletonBlock lines={4} />}
          {choiceSections.map((s) => {
            const c = s.choices!;
            if (s.key === "task_type") {
              return (
                <div key={s.key} role="radiogroup" aria-labelledby="tt-h" className="space-y-1">
                  <p id="tt-h" className="text-sm font-medium">{sectionTitle(s.key)} <span className="text-xs text-muted-foreground">(제안값: {c.proposed.map((x) => x.label).join(", ") || "없음"})</span></p>
                  <div className="flex flex-wrap gap-3">
                    {c.options.map((o) => (
                      <Label key={o.id} className="flex items-center gap-1.5 font-normal">
                        <input type="radio" name="task_type" value={o.id} checked={taskType === o.id} onChange={() => setTaskType(o.id)} className="size-4 accent-primary" />
                        {o.label}
                      </Label>
                    ))}
                  </div>
                </div>
              );
            }
            const value = s.key === "utilization" ? utilization : strategy;
            const setValue = s.key === "utilization" ? setUtilization : setStrategy;
            return (
              <div key={s.key} className="space-y-1">
                <p className="text-sm font-medium">{sectionTitle(s.key)} <span className="text-xs text-muted-foreground">(제안값: {c.proposed.map((x) => x.label).join(", ") || "없음"})</span></p>
                {c.options.length === 0 ? (
                  <p className="text-sm text-muted-foreground">선택지 목록이 비어 있어 빈칸으로 나갑니다.</p>
                ) : (
                  <div className="grid gap-1 sm:grid-cols-2">
                    {c.options.map((o) => (
                      <Label key={o.id} className="flex items-start gap-1.5 font-normal leading-snug">
                        <Checkbox
                          checked={value.includes(o.id)}
                          onChange={(e) => setValue(e.target.checked ? [...value, o.id] : value.filter((x) => x !== o.id))}
                          className="mt-0.5"
                        />
                        {o.label}
                      </Label>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </fieldset>

        <fieldset className="space-y-4 rounded-lg border p-4" disabled={!gate.ok}>
          <legend className="px-1 font-semibold">제안자 정보 (저장하지 않음)</legend>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="dept">제안부서</Label>
              <Input id="dept" value={proposer.department} onChange={set("department")} maxLength={100} autoComplete="organization" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="date">제안일자 (비우면 오늘)</Label>
              <Input id="date" value={proposer.proposed_on} onChange={set("proposed_on")} maxLength={20} placeholder="2026. 10. 27." autoComplete="off" />
            </div>
          </div>
          {(["p", "h"] as const).map((who) => (
            <div key={who} className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-1">
                <Label htmlFor={`${who}-rank`}>{who === "p" ? "제안자" : "부서장"} 직급</Label>
                <Input id={`${who}-rank`} value={proposer[`${who}_rank`]} onChange={set(`${who}_rank`)} maxLength={100} autoComplete="off" />
              </div>
              <div className="space-y-1">
                <Label htmlFor={`${who}-name`}>{who === "p" ? "제안자" : "부서장"} 성명</Label>
                <Input id={`${who}-name`} value={proposer[`${who}_name`]} onChange={set(`${who}_name`)} maxLength={100} autoComplete="off" />
              </div>
              <div className="space-y-1">
                <Label htmlFor={`${who}-phone`}>{who === "p" ? "제안자" : "부서장"} 연락처</Label>
                <Input id={`${who}-phone`} value={proposer[`${who}_phone`]} onChange={set(`${who}_phone`)} maxLength={100} autoComplete="off" inputMode="tel" />
              </div>
            </div>
          ))}
          <div className="space-y-1 sm:w-48">
            <Label htmlFor="ver">마무리할 버전</Label>
            <Select id="ver" value={version} onChange={(e) => setVersion(e.target.value === "" ? "" : Number(e.target.value))}>
              <option value="">최신 (v{run.draft_version})</option>
              {(draft.data?.versions ?? []).map((v) => (
                <option key={v} value={v}>v{v}</option>
              ))}
            </Select>
          </div>
        </fieldset>

        <ProblemBanner error={finalize.error} />
        <div className="flex flex-wrap items-center justify-end gap-2">
          {lastCheck && (
            <span className="text-sm text-muted-foreground" role="status">
              v{lastCheck.version} 파일 생성 · 렌더 점검 알림 {lastCheck.count}건
            </span>
          )}
          <Button type="submit" disabled={!gate.ok || finalize.isPending}>
            <Download aria-hidden="true" />
            {finalize.isPending ? "양식 만드는 중…" : "HWPX 내려받기"}
          </Button>
        </div>
      </form>

      <aside className="min-w-0">
        <section aria-labelledby="rc-h" className="rounded-lg border p-3">
          <h2 id="rc-h" className="mb-2 text-base font-semibold">렌더 전 점검</h2>
          {check.isPending ? (
            <SkeletonBlock lines={3} />
          ) : check.error ? (
            <ProblemBanner error={check.error} onRetry={() => check.refetch()} />
          ) : check.data ? (
            check.data.count === 0 ? (
              <p className="text-sm text-muted-foreground">알림이 없습니다.</p>
            ) : (
              <div className="space-y-2 text-sm">
                <p>알림 {check.data.count}건 — 렌더를 막지 않습니다.</p>
                {check.data.unsupported_numbers > 0 && (
                  <p className="font-medium text-warning">근거 없는 수치 알림 {check.data.unsupported_numbers}건 — 입력·근거에 없는 수치는 양식에서 직접 확인하거나 지우십시오.</p>
                )}
                <ul className="space-y-1">
                  {check.data.unresolved.map((p, i) => (
                    <li key={`u${i}`} className="flex flex-wrap gap-1">
                      <Badge variant={p.severity === "error" ? "destructive" : "warning"}>{p.severity}</Badge>
                      <span className="text-muted-foreground">{sectionTitle(p.section)}{p.sentence !== null ? ` 문장 ${p.sentence + 1}` : ""}:</span>
                      <UntrustedText text={p.message} />
                    </li>
                  ))}
                  {check.data.overflow.map((o, i) => (
                    <li key={`o${i}`}>
                      <Badge variant="warning">칸 길이 초과</Badge> {o.label} {o.chars}자 &gt; {o.limit}자 ({o.kind === "line" ? "한 줄 칸" : "본문 상한"})
                    </li>
                  ))}
                  {check.data.notes.map((n, i) => (
                    <li key={`n${i}`} className="text-muted-foreground"><UntrustedText text={n} /></li>
                  ))}
                </ul>
              </div>
            )
          ) : null}
        </section>
      </aside>
    </div>
  );
}
