import { ExternalLink } from "lucide-react";
import type {
  Analogy,
  Barrier,
  BarrierType,
  Maturity,
  NovelRecommendation,
  NovelRecommendations,
  NovelRef,
  NoveltyCoverage,
} from "@/api/types-novel";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { principleLabel } from "@/lib/labels";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { UntrustedText } from "@/components/UntrustedText";

/** 새 과제안 고르기 (신규 영역, ADR 0057) — [유사함] 0건·차단 없음일 때의 갈래. 계약 docs/contracts/novel-recommend.md §5·§8.
 *  글 칸은 모두 외부 LLM 출력·수집 문서 제목(비신뢰) → UntrustedText. 내부 문서 번호(doc_id)는 화면에 내지 않고
 *  refs·analogies 의 제목·자료원 이름만 보인다. [이 과제명으로 진행] 은 가제(title_hint) 칸에만 넣는다(서버 apply 없음). */

type Variant = NonNullable<BadgeProps["variant"]>;

const MATURITY_VARIANT: Record<Maturity, Variant> = {
  "즉시 적용": "success",
  "실증 필요": "info",
  "연구 필요": "warning",
};

const BARRIER_VARIANT: Record<BarrierType, Variant> = {
  수요: "info",
  규제: "warning",
  비용: "warning",
  기술: "secondary",
  운영: "outline",
};

/** 원문 링크는 http(s) 만 — 비신뢰 응답의 다른 스킴(javascript: 등)은 링크로 만들지 않는다 */
const safeUrl = (url: string | null | undefined): string | null => (url && /^https?:\/\//i.test(url) ? url : null);

/** coverage 한 줄 — 실시간 검색을 실제로 했는지(live)에 따라 범위를 다르게 말한다 */
function coverageSentence(c: NoveltyCoverage): string {
  const scope = c.live ? "저장 자료와 실시간 검색" : "저장 자료";
  return `${scope} 범위 안에서 기존 과제가 없습니다`;
}

export function NoveltyCoverageNote({ coverage }: { coverage: NoveltyCoverage }) {
  const labels = coverage.searched_labels.filter(Boolean);
  const unavailable = coverage.unavailable ?? [];
  return (
    <div className="rounded-md border bg-card p-3 text-sm" data-testid="novelty-coverage">
      <p className="font-medium">
        {coverageSentence(coverage)}
        {labels.length > 0 ? <span className="font-normal text-muted-foreground"> — 확인한 자료원: {labels.join("·")}</span> : null}
      </p>
      {unavailable.length > 0 && (
        <p className="mt-1 text-xs text-muted-foreground" data-testid="novel-unavailable">
          {unavailable.map((u) => `${u.label}: ${u.status_label}`).join(" · ")}
        </p>
      )}
    </div>
  );
}

function ExternalTitle({ title, url }: { title: string; url: string | null | undefined }) {
  const href = safeUrl(url);
  if (!href) return <UntrustedText text={title} className="font-medium" />;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-medium underline underline-offset-2">
      <UntrustedText text={title} />
      <ExternalLink aria-hidden="true" className="size-3 shrink-0" />
      <span className="sr-only">(새 창)</span>
    </a>
  );
}

export function AnalogyList({ items }: { items: Analogy[] }) {
  if (items.length === 0) return null;
  return (
    <section className="space-y-2" aria-labelledby="novel-analogies-heading" data-testid="novel-analogies">
      <h3 id="novel-analogies-heading" className="text-base font-semibold">
        다른 분야 사례
      </h3>
      <p className="text-xs text-muted-foreground">철도 밖에서 비슷한 문제를 다룬 자료입니다. 과제안의 참고일 뿐 근거로 그대로 쓰지 마십시오.</p>
      <ul className="space-y-2">
        {items.map((a, i) => (
          <li key={i} className="rounded-md border bg-card p-3 text-sm" data-testid="novel-analogy">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <ExternalTitle title={a.title} url={a.url} />
              <span className="flex shrink-0 gap-1">
                <Badge variant="secondary">참고</Badge>
              </span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              <UntrustedText text={a.domain_label} />
              {a.source_label && a.source_label !== a.domain_label ? ` · ${a.source_label}` : ""}
              {a.year ? ` · ${a.year}` : ""}
            </p>
            {a.why_relevant && <UntrustedText as="p" text={a.why_relevant} className="mt-1" />}
          </li>
        ))}
      </ul>
    </section>
  );
}

function RefLine({ r }: { r: NovelRef }) {
  return (
    <>
      <ExternalTitle title={r.title || "제목 없는 자료"} url={r.url} />
      {r.source_label ? <span className="text-muted-foreground"> · {r.source_label}</span> : null}
    </>
  );
}

function BarrierItem({ b, refs }: { b: Barrier; refs: NovelRef[] }) {
  const grounded = b.basis.level === "근거 있음";
  const basisRefs = grounded ? refs.filter((r) => b.basis.doc_ids.includes(r.doc_id)) : [];
  return (
    <li className="space-y-1" data-testid="novel-barrier">
      <p>
        <Badge variant={BARRIER_VARIANT[b.type] ?? "secondary"} className="mr-1" data-testid="barrier-type">
          {b.type}
        </Badge>
        <UntrustedText text={b.statement} />
      </p>
      <p className="text-xs">
        {grounded ? (
          <>
            <Badge variant="success" data-testid="barrier-basis">근거 있음</Badge>
            {basisRefs.length > 0 && (
              <span className="ml-1 text-muted-foreground">
                근거:{" "}
                {basisRefs.map((r, i) => (
                  <span key={r.doc_id}>
                    {i > 0 ? ", " : ""}
                    <UntrustedText text={r.title || "제목 없는 자료"} />
                    {r.source_label ? ` · ${r.source_label}` : ""}
                  </span>
                ))}
              </span>
            )}
          </>
        ) : (
          <>
            <Badge variant="warning" data-testid="barrier-basis">추정</Badge>
            <span className="ml-1 text-muted-foreground">
              — 확인 방법: <UntrustedText text={b.check || "정보 없음"} />
            </span>
          </>
        )}
      </p>
    </li>
  );
}

function NovelCard({
  card: c,
  titleHint,
  onUseTitle,
}: {
  card: NovelRecommendation;
  titleHint: string;
  onUseTitle: (title: string) => void;
}) {
  const headingId = `novel-card-${c.index}`;
  return (
    <Card data-testid="novel-card">
      <CardHeader>
        <CardTitle className="flex items-start justify-between gap-2 text-base">
          <span id={headingId}>
            <span className="sr-only">접근 방식: </span>
            <UntrustedText text={c.approach} />
          </span>
          <Badge variant={MATURITY_VARIANT[c.maturity] ?? "secondary"} className="shrink-0" data-testid="novel-maturity">
            {c.maturity}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <dl className="space-y-2">
          <div>
            <dt className="font-medium">요약</dt>
            <dd>
              <UntrustedText text={c.summary} />
            </dd>
          </div>
          {c.stages.length > 0 && (
            <div>
              <dt className="font-medium">단계</dt>
              <dd>
                <ol className="space-y-0.5" data-testid="novel-stages">
                  {c.stages.map((s, i) => (
                    <li key={i}>
                      {i > 0 ? (
                        <span aria-hidden="true" className="mr-1 text-muted-foreground">
                          →
                        </span>
                      ) : null}
                      <span className="font-medium">{s.stage}</span> <UntrustedText text={s.text} />
                    </li>
                  ))}
                </ol>
              </dd>
            </div>
          )}
          <div>
            <dt className="font-medium">첫 단계</dt>
            <dd>
              <UntrustedText text={c.first_step || "정보 없음"} />
            </dd>
          </div>
          <div>
            <dt className="font-medium">근거</dt>
            <dd className="text-xs">
              {c.refs.length === 0 ? (
                <span className="text-muted-foreground">없음</span>
              ) : (
                <ul className="list-disc space-y-0.5 pl-4" data-testid="novel-refs">
                  {c.refs.map((r) => (
                    <li key={r.doc_id}>
                      <RefLine r={r} />
                    </li>
                  ))}
                </ul>
              )}
            </dd>
          </div>
        </dl>

        {c.barriers.length > 0 && (
          <div>
            <h3 className="text-sm font-medium">넘어야 할 장벽</h3>
            <ul className="mt-1 space-y-2">
              {c.barriers.map((b, i) => (
                <BarrierItem key={i} b={b} refs={c.refs} />
              ))}
            </ul>
          </div>
        )}

        {c.titles.length > 0 && (
          <div>
            <h3 className="text-sm font-medium">장벽을 푸는 과제명</h3>
            <ul className="mt-1 space-y-2">
              {c.titles.map((t, i) => {
                const used = titleHint.trim() !== "" && titleHint.trim() === t.title.trim();
                return (
                  <li key={i} className="rounded-md border p-2" data-testid="novel-title">
                    <p className="flex flex-wrap items-center gap-1">
                      <UntrustedText text={t.title} className="font-medium" />
                      {t.resolves_types.length > 0 && (
                        <Badge variant="info" data-testid="title-resolves">
                          해소: {t.resolves_types.join("·")}
                        </Badge>
                      )}
                      {/* 문제 정의 카드의 모순에서 온 TRIZ 발명 원리 (ADR 0065) — 카드가 없으면 칸이 없거나 비어 있다 */}
                      {(t.principles ?? []).map((p) => (
                        <Badge key={p.number} variant="outline" className="whitespace-normal" data-testid="title-principle">
                          발명 원리 {principleLabel(p)}
                        </Badge>
                      ))}
                    </p>
                    {t.reason && <UntrustedText as="p" text={t.reason} className="mt-1 text-xs text-muted-foreground" />}
                    <Button
                      size="sm"
                      variant={used ? "outline" : "default"}
                      className="mt-2"
                      disabled={used}
                      onClick={() => onUseTitle(t.title)}
                      data-testid="novel-title-use"
                    >
                      {used ? "반영됨" : "이 과제명으로 진행"}
                    </Button>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** 새 과제안 갈래의 맥락(맨 위 coverage + 다른 분야 사례) — 추천 0건이어도 보인다 */
export function NovelContext({ rec }: { rec: NovelRecommendations }) {
  return (
    <div className="space-y-3">
      <NoveltyCoverageNote coverage={rec.coverage} />
      <AnalogyList items={rec.analogies ?? []} />
    </div>
  );
}

export function NovelPlans({
  rec,
  titleHint,
  onUseTitle,
  onTitleHintChange,
}: {
  rec: NovelRecommendations;
  /** 지금 가제(title_hint) 칸 값 */
  titleHint: string;
  onUseTitle: (title: string) => void;
  onTitleHintChange: (title: string) => void;
}) {
  const cards = rec.recommendations;
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        유사함으로 고른 기존 과제가 없어 새 영역의 과제안 {cards.length}건을 만들었습니다 — 바로 적용할 수 있는 안부터 놓았습니다(모델 출력 — 확인 뒤 사용).
        과제명을 고르면 가제 칸에 들어가고, 고친 뒤 그대로 진행할 수 있습니다.
      </p>
      <ul className="grid gap-3 md:grid-cols-2">
        {cards.map((c) => (
          <li key={c.index} id={`novel-rec-${c.index}`}>
            <NovelCard card={c} titleHint={titleHint} onUseTitle={onUseTitle} />
          </li>
        ))}
      </ul>
      <div className="space-y-1 rounded-md border bg-card p-3">
        <Label htmlFor="novel-title-hint">과제명(가제)</Label>
        <Input
          id="novel-title-hint"
          data-testid="novel-title-hint"
          value={titleHint}
          onChange={(e) => onTitleHintChange(e.target.value)}
          aria-describedby="novel-title-hint-help"
        />
        <p id="novel-title-hint-help" className="text-xs text-muted-foreground">
          [이 과제명으로 진행] 으로 넣은 과제명을 여기서 고칠 수 있습니다. 초안의 과제명은 이것으로 다듬어집니다.
        </p>
      </div>
    </div>
  );
}
