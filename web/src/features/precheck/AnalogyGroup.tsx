import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, ExternalLink } from "lucide-react";
import { analyzeAnalogyGroup, groupDocIds, NEEDS_SOURCE_TEXT } from "@/api/analogyGroups";
import type { Analogy, AnalogyGroupAnalysis, AnalogyGroupItem, AnalogyMember } from "@/api/types-novel";
import type { PrecheckRequest } from "@/api/types-precheck";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { UntrustedText } from "@/components/UntrustedText";

/** 비슷한 자료 묶음 (ADR 0065 덧붙임, 계약 problem-card.md 4.6절) — 대표 자료 카드 아래에 붙는다.
 *  비슷한 자료는 지우지 않고 접어 두고([비슷한 자료 N건 더 보기]), 목록이 그려진 뒤 뒤에서 AI 비교 분석을 불러
 *  표(핵심 방식·다른 점·활용할 점·한계)와 요약 두 줄을 채운다. 분석이 안 되면(꺼짐·실패·오류) 묶음만 보인다 — 알림 없음.
 *  글은 모두 수집 문서 제목·외부 LLM 출력(비신뢰) → UntrustedText. 내부 문서 번호는 화면에 내지 않는다. */

const SIMILAR_TOGGLE = (n: number) => `비슷한 자료 ${n}건 더 보기`;
const GROUP_WAITING = "비교 분석 중…";

const safeUrl = (url: string | null | undefined): string | null => (url && /^https?:\/\//i.test(url) ? url : null);

function TitleLink({ title, url }: { title: string; url: string | null | undefined }) {
  const href = safeUrl(url);
  const text = title || "제목 없는 자료";
  if (!href) return <UntrustedText text={text} className="font-medium" />;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-medium underline underline-offset-2">
      <UntrustedText text={text} />
      <ExternalLink aria-hidden="true" className="size-3 shrink-0" />
      <span className="sr-only">(새 창)</span>
    </a>
  );
}

function MemberLine({ m }: { m: AnalogyMember }) {
  return (
    <li data-testid="analogy-similar-item">
      <TitleLink title={m.title} url={m.url} />
      <span className="text-muted-foreground">
        {m.source_label ? ` · ${m.source_label}` : ""}
        {m.year ? ` · ${m.year}` : ""}
      </span>
    </li>
  );
}

/** 표의 한 칸 — 초록만으로 구분되지 않은 칸이면 옆에 [원문 보기] */
function Cell({ text, item, badge }: { text: string; item: AnalogyGroupItem; badge?: string }) {
  const href = item.needs_source && text === NEEDS_SOURCE_TEXT ? safeUrl(item.url) : null;
  return (
    <td className="px-3 py-2 align-top">
      {badge && (
        <Badge variant="warning" className="mr-1" data-testid="analogy-group-basis">
          {badge}
        </Badge>
      )}
      <UntrustedText text={text} />
      {href && (
        <>
          {" "}
          <a href={href} target="_blank" rel="noopener noreferrer" className="whitespace-nowrap underline underline-offset-2" data-testid="analogy-group-source-link">
            원문 보기<span className="sr-only"> (새 창)</span>
          </a>
        </>
      )}
    </td>
  );
}

export function AnalogyGroupTable({ analysis }: { analysis: AnalogyGroupAnalysis }) {
  const summary = analysis.summary;
  return (
    <div className="mt-2 space-y-2">
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full min-w-[44rem] text-xs" data-testid="analogy-group-table">
          <caption className="sr-only">비슷한 자료 비교 (AI 분석 — 초록 기준, 확인 뒤 사용)</caption>
          <thead className="bg-muted/50 text-left">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">자료</th>
              <th scope="col" className="px-3 py-2 font-medium">핵심 방식</th>
              <th scope="col" className="px-3 py-2 font-medium">다른 점</th>
              <th scope="col" className="px-3 py-2 font-medium">이 과제에 활용할 점</th>
              <th scope="col" className="px-3 py-2 font-medium">한계</th>
            </tr>
          </thead>
          <tbody>
            {analysis.items.map((it, i) => (
              <tr key={i} className="border-t" data-testid="analogy-group-row">
                <th scope="row" className="px-3 py-2 text-left align-top font-normal">
                  <TitleLink title={it.title} url={it.url} />
                  <span className="block text-muted-foreground">
                    {[it.source_label, it.year ? String(it.year) : ""].filter(Boolean).join(" · ")}
                  </span>
                </th>
                <Cell text={it.core_method} item={it} />
                <Cell text={it.difference} item={it} />
                <Cell text={it.use} item={it} badge={it.use_basis || "추정"} />
                <Cell text={it.limit} item={it} />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {summary && (summary.common || summary.gap) && (
        <dl className="space-y-1 text-xs" data-testid="analogy-group-summary">
          {summary.common && (
            <div>
              <dt className="inline font-semibold">공통 접근</dt>
              <dd className="inline">
                {" — "}
                <UntrustedText text={summary.common} />
              </dd>
            </div>
          )}
          {summary.gap && (
            <div>
              <dt className="inline font-semibold">아직 다뤄지지 않은 부분</dt>
              <dd className="inline">
                {" — "}
                <UntrustedText text={summary.gap} />
              </dd>
            </div>
          )}
        </dl>
      )}
      <p className="text-xs text-muted-foreground">AI가 제목과 초록만 보고 비교했습니다 — 확인 뒤 사용하십시오.</p>
    </div>
  );
}

/** 묶음 하나의 비교 분석을 뒤에서 부른다. 같은 묶음은 화면이 다시 그려져도 한 번만 부른다(문서 묶음이 키).
 *  요청 몸통은 처음 부를 때의 것 — 가제 칸을 고쳐도 다시 부르지 않는다. */
function useGroupAnalysis(docIds: string[], request: PrecheckRequest | undefined, enabled: boolean) {
  const latest = React.useRef(request);
  latest.current = request;
  return useQuery({
    queryKey: ["analogy-group", [...docIds].sort().join("|")],
    queryFn: ({ signal }) => analyzeAnalogyGroup(latest.current as PrecheckRequest, docIds, { signal }),
    enabled: enabled && !!request && docIds.length >= 2,
    staleTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
}

/** 대표 자료 카드 아래 — 접힘 버튼 + (뒤에서 채워지는) 비교 표 */
export function AnalogyGroup({
  item,
  request,
  analyze,
}: {
  item: Analogy;
  /** 비교 분석에 보낼 입력(과제안 요청과 같은 몸통) — 없으면 분석하지 않는다 */
  request?: PrecheckRequest;
  /** 이 묶음을 분석할 차례인가(한 화면 상한 안) */
  analyze: boolean;
}) {
  const members = item.similar ?? [];
  const [open, setOpen] = React.useState(false);
  const listId = React.useId();
  const q = useGroupAnalysis(groupDocIds(item), request, analyze);
  const ok = q.data && q.data.status === "ok" && q.data.items.length > 0 ? q.data : null;
  if (members.length === 0) return null;
  return (
    <div className="mt-2 border-t pt-2" data-testid="analogy-group">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-auto px-1 py-0.5 text-xs"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((v) => !v)}
        data-testid="analogy-similar-toggle"
      >
        {open ? <ChevronDown aria-hidden="true" /> : <ChevronRight aria-hidden="true" />}
        {SIMILAR_TOGGLE(members.length)}
      </Button>
      <ul id={listId} hidden={!open} className="mt-1 list-disc space-y-0.5 pl-5 text-xs" data-testid="analogy-similar-list">
        {members.map((m, i) => (
          <MemberLine key={i} m={m} />
        ))}
      </ul>
      {q.isFetching && !ok && (
        <p role="status" className="mt-1 text-xs text-muted-foreground" data-testid="analogy-group-waiting">
          {GROUP_WAITING}
        </p>
      )}
      {ok && <AnalogyGroupTable analysis={ok} />}
    </div>
  );
}
