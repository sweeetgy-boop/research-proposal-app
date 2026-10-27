import type { Score } from "@/api/types";
import { UntrustedText } from "./UntrustedText";
import { cn } from "@/lib/utils";

/** 심사 기준 4개 점수(1~5). delta 가 있으면 1차 대비 변화. */
export function ScoreTable({ scores, delta, caption }: { scores: Score[]; delta?: Record<string, number>; caption: string }) {
  if (scores.length === 0) {
    return <p className="text-sm text-muted-foreground">점수가 없습니다 (검토 모델이 채점을 돌려주지 않았습니다).</p>;
  }
  return (
    <table className="w-full text-sm">
      <caption className="sr-only">{caption}</caption>
      <thead>
        <tr className="border-b text-left text-muted-foreground">
          <th scope="col" className="py-1 pr-2 font-medium">기준</th>
          <th scope="col" className="py-1 pr-2 font-medium">점수</th>
          {delta && <th scope="col" className="py-1 pr-2 font-medium">변화</th>}
          <th scope="col" className="py-1 font-medium">근거</th>
        </tr>
      </thead>
      <tbody>
        {scores.map((s) => {
          const d = delta?.[s.criterion];
          return (
            <tr key={s.criterion} className="border-b align-top">
              <th scope="row" className="py-1.5 pr-2 font-medium">{s.criterion}</th>
              <td className={cn("py-1.5 pr-2 tabular-nums", s.weak && "font-semibold text-warning")}>
                {s.score}/5{s.weak && <span className="sr-only"> (낮음)</span>}
              </td>
              {delta && (
                <td className={cn("py-1.5 pr-2 tabular-nums", d && d > 0 && "text-success", d && d < 0 && "text-destructive")}>
                  {d === undefined ? "—" : d > 0 ? `+${d}` : `${d}`}
                </td>
              )}
              <td className="py-1.5"><UntrustedText text={s.reason} /></td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
