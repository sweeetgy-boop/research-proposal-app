import { LocalSuggestionCard, LocalVerdictBadge } from "@/features/draft/LocalReview";
import * as React from "react";
import { useNavigate, useSearchParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { CloudOff, CloudUpload, Landmark, MessageCircleQuestion, Save, Wand2 } from "lucide-react";
import { useRunContext } from "./useRunContext";
import { keys, useDraft, useDraftReview, useFinalReview, useSaveVersion, useVersion, useWorking } from "@/api/hooks";
import { deleteWorking, putWorking } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import { DraftEditor } from "@/features/draft/DraftEditor";
import { SectionRewrite } from "@/features/rewrite/SectionRewrite";
import { SectionQuestions } from "@/features/rewrite/SectionQuestions";
import { FigureList } from "@/features/figures/FigureList";
import { AddFigureDialog } from "@/features/figures/AddFigureDialog";
import { FigureJobBanner } from "@/features/figures/FigureJobBanner";
import { figuresDrawing, slotsFor } from "@/features/figures/figureJob";
import { countChanges, emptyEditState, fromWorking, isDirty, toEditRequest, toWorking, usableRevisions, type EditState } from "@/features/draft/editModel";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { useToast } from "@/components/ui/toast";
import { formatDate } from "@/lib/utils";
import { sectionTitle } from "@/lib/sections";
import { WriterBadges } from "@/features/draft/WriterBadges";
import { editAiKeys, useChanges } from "@/api/editai";
import { RunPolicyDialog } from "@/features/policy/RunPolicyDialog";
import { ChangeCount, SaveVersionDialog } from "@/features/versions/SaveVersionFlow";

const EDITABLE = new Set(["drafted", "editing", "final_reviewed"]);
type SaveState = { kind: "idle" } | { kind: "saving" } | { kind: "saved"; at: string } | { kind: "error"; error: unknown };

export default function Edit() {
  const { run, refetch } = useRunContext();
  const id = run.run_id;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { toast } = useToast();
  const draft = useDraft(id);
  const current = draft.data?.version ?? null;
  const version = useVersion(id, current);
  const draftReview = useDraftReview(id);
  const finalReview = useFinalReview(id, run.flow.final_reviews > 0);
  const working = useWorking(id);
  const save = useSaveVersion(id);
  const [state, setState] = React.useState<EditState>(emptyEditState);
  const [autosave, setAutosave] = React.useState<SaveState>({ kind: "idle" });
  const [conflict, setConflict] = React.useState<unknown>(null);
  const [offeredWorking, setOfferedWorking] = React.useState(false);
  const [rewriteKey, setRewriteKey] = React.useState<string | null>(null);
  const [questionsKey, setQuestionsKey] = React.useState<string | null>(null);
  const [policyOpen, setPolicyOpen] = React.useState(false);
  const [saveAsk, setSaveAsk] = React.useState<{ kind: "none" | "saved" | "already"; version: number | null } | null>(null);
  const editable = EDITABLE.has(run.status) && !run.legacy;
  const changes = useChanges(id, editable);
  // ⑥ 제출 전 점검 [정책 근거 넣기] → ?policy=1 로 들어오면 대화상자를 바로 연다 (ADR 0052)
  const [params, setParams] = useSearchParams();
  React.useEffect(() => {
    if (params.get("policy") !== "1") return;
    setPolicyOpen(true);
    const next = new URLSearchParams(params);
    next.delete("policy");
    setParams(next, { replace: true });
  }, [params, setParams]);

  const revisions = React.useMemo(
    () => usableRevisions([...(finalReview.data?.comments ?? []), ...(draftReview.data?.comments ?? [])]),
    [finalReview.data, draftReview.data],
  );
  const sections = version.data?.sections ?? [];
  const dirty = isDirty(state);
  const policyBlocked = !editable
    ? run.legacy
      ? "예전 방식으로 만든 제안서는 조회만 됩니다"
      : "검토 중이거나 마무리된 제안서라 지금은 넣을 수 없습니다 — 마무리된 제안서는 ⑥ 최종 마무리에서 다시 연 뒤 넣으십시오"
    : dirty
      ? "저장하지 않은 편집이 있어 고를 수 없습니다 — 먼저 [새 버전으로 저장] 하십시오"
      : undefined;
  /** 2-가-(1) 머리의 [정책 근거 넣기·바꾸기] — 편집할 수 없을 때도 보인다(누르면 이유). 비어 있으면 주 색 */
  const policyButton = (sec: { sentences: unknown[] }) => (
    <Button type="button" variant={sec.sentences.length ? "outline" : "default"} size="sm" onClick={() => setPolicyOpen(true)}>
      <Landmark aria-hidden="true" />
      정책 근거 넣기·바꾸기
    </Button>
  );
  const figures = draft.data?.figures ?? [];
  // 그림 동작은 새 버전을 만든다 — 저장하지 않은 편집이 있으면 기준 버전이 어긋나므로 막는다
  const figuresDisabled = !editable || dirty;
  const onFigureApplied = (v: number) => {
    // 그림 확인·추천 그림 결정은 상태 표시 — 버전이 그대로면 새 버전 없이 표시만 저장 (항목 21)
    toast(v === current ? "확인 표시를 저장했습니다 (새 버전 없음)" : `v${v} 으로 저장했습니다 (그림)`, "success");
    refetch();
    qc.invalidateQueries({ queryKey: keys.run(id) });
    qc.invalidateQueries({ queryKey: editAiKeys.changes(id) });
  };

  // 임시 저장(autosave): 편집이 바뀌고 1.5초 뒤 서버 작업 사본에 쓴다 (localStorage 없음).
  React.useEffect(() => {
    if (!editable || !dirty || current === null || sections.length === 0) return;
    const t = window.setTimeout(async () => {
      setAutosave({ kind: "saving" });
      try {
        await putWorking(id, toWorking(sections, state, current, revisions));
        setAutosave({ kind: "saved", at: new Date().toISOString() });
      } catch (error) {
        setAutosave({ kind: "error", error });
      }
    }, 1500);
    return () => window.clearTimeout(t);
  }, [state, dirty, editable, id, current, sections, revisions]);

  const applyWorking = () => {
    if (working.data) setState(fromWorking(working.data.working, sections));
    setOfferedWorking(true);
  };
  const discardWorking = async () => {
    setOfferedWorking(true);
    try {
      await deleteWorking(id);
      qc.invalidateQueries({ queryKey: keys.working(id) });
    } catch {
      /* ignore */
    }
  };

  /** [새 버전으로 저장] — 항상 누를 수 있다. 저장하지 않은 편집이 있으면 새 버전으로 저장한 뒤, 없으면 바로
   *  "최종 검토로 넘어갈까요?" 를 묻는다(바로 저장된 변경 — 그림·근거·정책 근거·보완 메모 — 도 변경으로 센다). */
  const doSave = async () => {
    if (current === null) return;
    const serverTotal = changes.data?.total ?? 0;
    if (!dirty) {
      setSaveAsk(serverTotal > 0 ? { kind: "already", version: current } : { kind: "none", version: null });
      return;
    }
    try {
      const out = await save.mutateAsync(toEditRequest(state, current, revisions));
      setState(emptyEditState());
      setAutosave({ kind: "idle" });
      refetch();
      qc.invalidateQueries({ queryKey: editAiKeys.changes(id) });
      if (out.version === current) setSaveAsk(serverTotal > 0 ? { kind: "already", version: current } : { kind: "none", version: null });
      else {
        toast(`v${out.version} 으로 저장했습니다.`, "success");
        setSaveAsk({ kind: "saved", version: out.version });
      }
    } catch (e) {
      if (isApiError(e) && e.status === 409) setConflict(e);
    }
  };

  const reloadLatest = async () => {
    setConflict(null);
    setState(emptyEditState());
    await qc.invalidateQueries({ queryKey: keys.run(id) });
  };

  if (draft.isPending || (current !== null && version.isPending)) {
    return (
      <div className="space-y-4" aria-busy="true">
        <SkeletonBlock lines={2} />
        <SkeletonBlock lines={10} />
      </div>
    );
  }
  if (draft.error) return <ProblemBanner error={draft.error} onRetry={() => draft.refetch()} />;
  if (version.error) return <ProblemBanner error={version.error} onRetry={() => version.refetch()} />;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">④ 직접 수정 — v{current} 기준</h2>
          <p className="text-sm text-muted-foreground">문장마다 원문 유지·수정안 사용·직접 수정·삭제·뒤에 추가를 고르고 저장하면 새 버전이 됩니다. AI 다시 쓰기·보완 질문은 누를 때만 Argon 을 부릅니다(실패하면 로컬 모델).</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <AddFigureDialog runId={id} baseVersion={current ?? 0} disabled={figuresDisabled || figuresDrawing(run)} onApplied={onFigureApplied} />
            {editable && dirty && <span className="text-xs text-muted-foreground">그림은 편집을 저장한 뒤 바꿀 수 있습니다.</span>}
            {figuresDrawing(run) && <span className="text-xs text-muted-foreground">그림을 다 그린 뒤 그림을 추가할 수 있습니다.</span>}
          </div>
        </div>
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground" role="status" aria-live="polite">
          {autosave.kind === "saving" && (
            <>
              <CloudUpload className="size-4" aria-hidden="true" /> 임시 저장 중…
            </>
          )}
          {autosave.kind === "saved" && (
            <>
              <CloudUpload className="size-4 text-success" aria-hidden="true" /> 임시 저장됨 {formatDate(autosave.at)}
            </>
          )}
          {autosave.kind === "error" && (
            <>
              <CloudOff className="size-4 text-destructive" aria-hidden="true" /> 임시 저장 실패
            </>
          )}
          {autosave.kind === "idle" && dirty && "바뀐 내용 있음"}
        </p>
      </div>

      {!editable && (
        <Alert variant="warning">
          <CloudOff aria-hidden="true" />
          <div>
            <AlertTitle>지금은 편집할 수 없습니다</AlertTitle>
            <AlertDescription>
              {run.legacy ? "예전 방식으로 만든 제안서는 조회만 됩니다." : "검토 중이거나 마무리된 제안서입니다. 마무리된 제안서는 최종 마무리 화면에서 다시 열 수 있습니다."}
            </AlertDescription>
          </div>
        </Alert>
      )}

      {editable && working.data && !offeredWorking && !dirty && (
        <Alert variant="info">
          <CloudUpload aria-hidden="true" />
          <div className="flex-1">
            <AlertTitle>임시 저장이 있습니다 ({formatDate(working.data.working.saved_at)})</AlertTitle>
            <AlertDescription>저장하지 않은 편집이 서버에 남아 있습니다. 불러오면 섹션 통문으로 복원됩니다.</AlertDescription>
            <div className="mt-2 flex gap-2">
              <Button size="sm" onClick={applyWorking}>
                불러오기
              </Button>
              <Button size="sm" variant="outline" onClick={discardWorking}>
                버리기
              </Button>
            </div>
          </div>
        </Alert>
      )}

      <ProblemBanner error={save.error && !(isApiError(save.error) && save.error.status === 409) ? save.error : null} />

      <FigureJobBanner run={run} ready={figures.length} baseVersion={current ?? 0} disabled={figuresDisabled} onApplied={onFigureApplied} />

      <DraftEditor
        sections={sections}
        annotations={version.data?.annotations ?? []}
        revisions={revisions}
        state={state}
        onChange={setState}
        disabled={!editable}
        sectionTools={(sec) =>
          editable && sec.key !== "title" ? (
            <span className="flex flex-wrap gap-1">
              {sec.key === "policy_importance" && policyButton(sec)}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setRewriteKey(sec.key)}
                aria-label={`${sectionTitle(sec.key)} ${sec.sentences.length ? "AI 다시 쓰기" : "AI 새로 쓰기"}`}
              >
                <Wand2 aria-hidden="true" />
                {sec.sentences.length ? "AI 다시 쓰기" : "AI 새로 쓰기"}
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => setQuestionsKey(sec.key)} aria-label={`${sectionTitle(sec.key)} 보완 질문`}>
                <MessageCircleQuestion aria-hidden="true" />
                보완 질문
              </Button>
            </span>
          ) : sec.key === "policy_importance" ? (
            policyButton(sec)
          ) : null
        }
        sentenceBadges={(s) => <LocalVerdictBadge verdict={draft.data?.local_check?.verdicts?.[s.sentence_id]} />}
        sentenceExtra={(s) => {
          const sugg = draft.data?.local_check?.suggestions?.[s.sentence_id];
          return sugg ? (
            <LocalSuggestionCard
              runId={id}
              suggestion={sugg}
              baseVersion={current ?? 0}
              disabled={!editable || dirty || run.flow.has_working}
              disabledReason={dirty || run.flow.has_working ? "저장하지 않은 편집이 있어 먼저 저장하십시오." : undefined}
            />
          ) : null;
        }}
        sectionBadges={(sec) => (
          <WriterBadges
            local={(draft.data?.local_sections ?? []).includes(sec.key)}
            writer={draft.data?.writers?.[sec.key]}
            fallback={(draft.data?.fallback_sections ?? []).find((f) => f.key === sec.key)}
          />
        )}
        sectionExtra={(sec) =>
          sec.key !== "title" ? (
            <>
              {sec.key === "policy_importance" && sec.sentences.length === 0 && (
                <p className="mb-3 flex flex-wrap items-center gap-2 rounded-md border border-dashed border-primary/50 bg-primary-soft p-3 text-sm" data-testid="policy-empty">
                  <span>정책 근거가 없습니다 — 이대로면 2-가-(1) 이 빈칸으로 남습니다.</span>
                  <Button type="button" size="sm" onClick={() => setPolicyOpen(true)}>
                    정책 근거 넣기
                  </Button>
                </p>
              )}
              <FigureList runId={id} figures={figures} section={sec.key} baseVersion={current ?? 0} disabled={figuresDisabled} onApplied={onFigureApplied} slots={slotsFor(run, sec.key)} />
            </>
          ) : null
        }
      />

      <SectionRewrite
        runId={id}
        sectionKey={rewriteKey}
        baseVersion={current ?? 0}
        dirty={dirty}
        onClose={() => setRewriteKey(null)}
        onApplied={(v) => {
          setRewriteKey(null);
          setState(emptyEditState());
          setAutosave({ kind: "idle" });
          toast(v === current ? "바뀐 내용이 없어 새 버전을 만들지 않았습니다." : `AI 다시 쓰기를 v${v} 으로 반영했습니다.`, "success");
          refetch();
          qc.invalidateQueries({ queryKey: editAiKeys.changes(id) });
        }}
        onPolicy={() => {
          setRewriteKey(null);
          setPolicyOpen(true);
        }}
      />
      <SectionQuestions
        runId={id}
        sectionKey={questionsKey}
        onClose={() => setQuestionsKey(null)}
        onRewrite={(key) => {
          setQuestionsKey(null);
          setRewriteKey(key);
        }}
      />
      <RunPolicyDialog
        runId={id}
        open={policyOpen}
        baseVersion={current ?? 0}
        disabled={policyBlocked !== undefined}
        disabledReason={policyBlocked}
        onClose={() => setPolicyOpen(false)}
        onApplied={(v) => {
          setPolicyOpen(false);
          toast(v === current ? "바뀐 내용이 없어 새 버전을 만들지 않았습니다." : `정책 근거를 v${v} 으로 반영했습니다.`, "success");
          refetch();
          qc.invalidateQueries({ queryKey: editAiKeys.changes(id) });
        }}
      />

      <div className="sticky bottom-[var(--stepnav-h)] z-20 -mx-4 flex flex-wrap items-end gap-3 border-t bg-background/95 px-4 py-3 backdrop-blur">
        <div className="min-w-0 flex-1 space-y-1">
          <Label htmlFor="note">저장 메모 (선택, 200자)</Label>
          <Input id="note" value={state.note} maxLength={200} onChange={(e) => setState({ ...state, note: e.target.value })} disabled={!editable} />
        </div>
        <ChangeCount local={countChanges(state)} server={changes.data} />
        <Button onClick={doSave} disabled={!editable || save.isPending}>
          <Save aria-hidden="true" />
          {save.isPending ? "저장 중…" : "새 버전으로 저장"}
        </Button>
      </div>

      <SaveVersionDialog
        open={saveAsk !== null}
        kind={saveAsk?.kind ?? "none"}
        savedVersion={saveAsk?.version}
        onCancel={() => setSaveAsk(null)}
        onConfirm={() => {
          setSaveAsk(null);
          navigate(`/runs/${id}/final-review`);
        }}
      />

      <Dialog
        open={conflict !== null}
        onClose={() => setConflict(null)}
        title="다른 곳에서 먼저 저장되었습니다"
        description={isApiError(conflict) ? conflict.problem.detail : undefined}
        footer={
          <>
            <Button variant="outline" onClick={() => setConflict(null)}>
              닫기
            </Button>
            <Button onClick={reloadLatest}>최신 버전 불러오기</Button>
          </>
        }
      >
        <p className="text-sm">기준 버전이 바뀌어 이 편집을 그대로 저장할 수 없습니다. 최신 버전을 불러오면 지금 편집은 버려집니다 (임시 저장은 서버에 남습니다).</p>
      </Dialog>
    </div>
  );
}
