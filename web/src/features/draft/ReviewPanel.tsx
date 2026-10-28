import * as React from "react";
import { Eye } from "lucide-react";
import type { ReviewOut } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { ScoreTable } from "@/components/ScoreTable";
import { UntrustedText } from "@/components/UntrustedText";
import { sectionTitle } from "@/lib/sections";
import { reasonLabel } from "@/lib/labels";

const STATUS: Record<string, { label: string; variant: "secondary" | "success" | "outline" | "destructive" }> = {
  open: { label: "미처리", variant: "secondary" },
  resolved: { label: "반영됨", variant: "success" },
  discarded: { label: "폐기", variant: "destructive" },
};

export function ReviewPanel({ review, title }: { review: ReviewOut; title: string }) {
  const [candidate, setCandidate] = React.useState<string | null>(null);
  const candidates = review.candidate_choices ?? {};
  const candidateKeys = Object.keys(candidates);
  const applied = new Set(review.applied_ids);

  return (
    <section aria-labelledby="review-h" className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="review-h" className="text-lg font-semibold">
          {title}
        </h2>
        <Badge variant="outline">
          {review.transfer.provider ?? "—"} / {review.transfer.model ?? "—"}
        </Badge>
        {review.status === "skipped" && <Badge variant="warning">건너뜀 ({reasonLabel(review.skipped_reason)})</Badge>}
        {review.status === "error" && <Badge variant="destructive">오류</Badge>}
        {review.applied_version && <Badge variant="success">v{review.applied_version} 에 {review.applied_ids.length}건 자동 반영</Badge>}
        {typeof review.checklist_coverage === "number" && (
          <Badge variant="info">체크리스트 충족 {Math.round(review.checklist_coverage * 100)}%</Badge>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        외부 전송: 문장 {review.transfer.sentences_sent}건, 공개 자료 {review.transfer.public_doc_ids.length}건, 사내 자료 {review.transfer.internal_doc_ids.length}건,
        호출 {review.transfer.calls}회. 의견과 수정안은 모델 출력(비신뢰)입니다.
      </p>

      <div className="rounded-lg border p-3">
        <h3 className="mb-2 text-sm font-semibold">심사 기준 점수</h3>
        <ScoreTable scores={review.scores} delta={review.kind === "final" ? review.score_delta : undefined} caption={`${title} 점수`} />
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold">의견 {review.comments.length}건</h3>
        {review.comments.length === 0 ? (
          <p className="text-sm text-muted-foreground">의견이 없습니다.</p>
        ) : (
          <ul className="space-y-2">
            {review.comments.map((c) => {
              const st = STATUS[c.status] ?? STATUS.open!;
              return (
                <li key={c.id} className="rounded-md border p-3 text-sm">
                  <div className="mb-1 flex flex-wrap items-center gap-1.5">
                    <span className="font-mono text-xs text-muted-foreground">{c.id}</span>
                    <Badge variant="outline">{sectionTitle(c.section)}{c.sentence !== null ? ` 문장 ${c.sentence + 1}` : " (섹션)"}</Badge>
                    <Badge variant="secondary">{c.issue_type}</Badge>
                    {c.kind === "addition" && <Badge variant="info">추가 문장</Badge>}
                    <Badge variant={st.variant}>{applied.has(c.id) ? "자동 반영" : st.label}</Badge>
                    {c.discard_reason && <span className="text-xs text-destructive">폐기 사유: {c.discard_reason}</span>}
                  </div>
                  <UntrustedText as="p" text={c.comment} />
                  {c.revised_text && (
                    <p className="mt-1 rounded bg-muted/60 p-2">
                      <span className="font-medium">{c.kind === "addition" ? "추가안: " : "수정안: "}</span>
                      <UntrustedText text={c.revised_text} />
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {candidateKeys.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold">두 후보 중 선택 {candidateKeys.length}개 섹션</h3>
          <ul className="flex flex-wrap gap-2">
            {candidateKeys.map((k) => (
              <li key={k}>
                <Button variant="outline" size="sm" onClick={() => setCandidate(k)}>
                  <Eye aria-hidden="true" />
                  {sectionTitle(k)} 다른 후보 보기
                </Button>
              </li>
            ))}
          </ul>
          <Dialog open={candidate !== null} onClose={() => setCandidate(null)} title={candidate ? `${sectionTitle(candidate)} — 선택되지 않은 후보` : ""}>
            {candidate && (
              <div className="space-y-2 text-sm">
                {candidates[candidate]?.reason && (
                  <p>
                    <span className="font-medium">선택 이유: </span>
                    <UntrustedText text={String(candidates[candidate]?.reason)} />
                  </p>
                )}
                <UntrustedText as="p" text={candidates[candidate]?.rejected_text ?? "(후보 본문 없음)"} className="rounded bg-muted/60 p-2" />
              </div>
            )}
          </Dialog>
        </div>
      )}
    </section>
  );
}
