import * as React from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { CloudOff, CloudUpload, MessageCircleQuestion, Save, Wand2 } from "lucide-react";
import { useRunContext } from "./useRunContext";
import { keys, useDraft, useDraftReview, useFinalReview, useSaveVersion, useVersion, useWorking } from "@/api/hooks";
import { deleteWorking, putWorking } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import { DraftEditor } from "@/features/draft/DraftEditor";
import { SectionRewrite } from "@/features/rewrite/SectionRewrite";
import { SectionQuestions } from "@/features/rewrite/SectionQuestions";
import { FigureList } from "@/features/figures/FigureList";
import { AddFigureDialog } from "@/features/figures/AddFigureDialog";
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
  const editable = EDITABLE.has(run.status) && !run.legacy;

  const revisions = React.useMemo(
    () => usableRevisions([...(finalReview.data?.comments ?? []), ...(draftReview.data?.comments ?? [])]),
    [finalReview.data, draftReview.data],
  );
  const sections = version.data?.sections ?? [];
  const dirty = isDirty(state);
  const figures = draft.data?.figures ?? [];
  // 그림 동작은 새 버전을 만든다 — 저장하지 않은 편집이 있으면 기준 버전이 어긋나므로 막는다
  const figuresDisabled = !editable || dirty;
  const onFigureApplied = (v: number) => {
    toast(`v${v} 으로 저장했습니다 (그림)`, "success");
    refetch();
    qc.invalidateQueries({ queryKey: keys.run(id) });
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

  const doSave = async () => {
    if (current === null) return;
    try {
      const out = await save.mutateAsync(toEditRequest(state, current, revisions));
      setState(emptyEditState());
      setAutosave({ kind: "idle" });
      if (out.version === current) toast("바뀐 내용이 없어 새 버전을 만들지 않았습니다.");
      else toast(`v${out.version} 으로 저장했습니다.`, "success");
      refetch();
      navigate(`/runs/${id}/draft`);
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
          <p className="text-sm text-muted-foreground">문장마다 원문 유지·수정안 사용·직접 수정·삭제·뒤에 추가를 고르고 저장하면 새 버전이 됩니다. 이 단계에서는 외부 모델을 부르지 않습니다.</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <AddFigureDialog runId={id} baseVersion={current ?? 0} disabled={figuresDisabled} onApplied={onFigureApplied} />
            {editable && dirty && <span className="text-xs text-muted-foreground">그림은 편집을 저장한 뒤 바꿀 수 있습니다.</span>}
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
              {run.legacy ? "옛 run 은 조회만 됩니다." : "검토 중이거나 마무리된 run 입니다. 마무리된 run 은 최종 마무리 화면에서 다시 열 수 있습니다."}
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
              <Button type="button" variant="outline" size="sm" onClick={() => setRewriteKey(sec.key)} aria-label={`${sectionTitle(sec.key)} AI 다시 쓰기`}>
                <Wand2 aria-hidden="true" />
                AI 다시 쓰기
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => setQuestionsKey(sec.key)} aria-label={`${sectionTitle(sec.key)} 보완 질문`}>
                <MessageCircleQuestion aria-hidden="true" />
                보완 질문
              </Button>
            </span>
          ) : null
        }
        sectionExtra={(sec) =>
          sec.key !== "title" ? (
            <FigureList runId={id} figures={figures} section={sec.key} baseVersion={current ?? 0} disabled={figuresDisabled} onApplied={onFigureApplied} />
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
        }}
      />
      <SectionQuestions runId={id} sectionKey={questionsKey} onClose={() => setQuestionsKey(null)} />

      <div className="sticky bottom-0 -mx-4 flex flex-wrap items-end gap-3 border-t bg-background/95 px-4 py-3 backdrop-blur">
        <div className="min-w-0 flex-1 space-y-1">
          <Label htmlFor="note">저장 메모 (선택, 200자)</Label>
          <Input id="note" value={state.note} maxLength={200} onChange={(e) => setState({ ...state, note: e.target.value })} disabled={!editable} />
        </div>
        <span className="text-sm text-muted-foreground">변경 {countChanges(state)}건</span>
        <Button onClick={doSave} disabled={!editable || !dirty || save.isPending}>
          <Save aria-hidden="true" />
          {save.isPending ? "저장 중…" : "새 버전으로 저장"}
        </Button>
      </div>

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
