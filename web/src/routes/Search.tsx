import * as React from "react";
import { Search as SearchIcon } from "lucide-react";
import { useSearch } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { ProblemBanner } from "@/components/ProblemBanner";
import { EmptyState } from "@/components/EmptyState";
import { UntrustedText } from "@/components/UntrustedText";

export default function Search() {
  const [input, setInput] = React.useState("");
  const [q, setQ] = React.useState("");
  const res = useSearch(q);
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">자료 검색</h1>
      <p className="text-sm text-muted-foreground">사내 과제·공시 요약·논문 청크를 키워드+벡터(RRF)로 찾습니다. 결과는 수집 자료(비신뢰 텍스트)입니다.</p>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setQ(input.trim());
        }}
        role="search"
      >
        <div className="min-w-0 flex-1 space-y-1.5">
          <Label htmlFor="q">검색어</Label>
          <Input id="q" value={input} onChange={(e) => setInput(e.target.value)} maxLength={500} />
        </div>
        <Button type="submit" disabled={!input.trim()}>
          <SearchIcon aria-hidden="true" />
          검색
        </Button>
      </form>
      <div aria-live="polite" className="min-h-40">
        {res.isFetching && <SkeletonBlock lines={4} />}
        <ProblemBanner error={res.error} onRetry={() => res.refetch()} />
        {res.data && res.data.chunks.length === 0 && <EmptyState title="결과 없음" description="다른 검색어로 다시 찾아보십시오." />}
        {res.data && res.data.chunks.length > 0 && (
          <ol className="space-y-2">
            {res.data.chunks.map((c) => (
              <li key={c.chunk_id} className="rounded-lg border p-3 text-sm">
                <div className="mb-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                  <span className="font-mono">{c.doc_id}</span>
                  <Badge variant="outline">#{c.ordinal}</Badge>
                  {c.basis && <Badge variant="secondary">{c.basis}</Badge>}
                  {c.similarity !== null && <span className="tabular-nums">유사도 {c.similarity.toFixed(3)}</span>}
                  <Badge variant="warning">비신뢰</Badge>
                </div>
                <UntrustedText as="p" text={c.text} />
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
