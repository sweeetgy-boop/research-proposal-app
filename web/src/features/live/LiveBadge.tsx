import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/** [4] 실시간 검색에서 찾은 자료 표시. 글자 자체가 뜻을 전한다(색만으로 구분하지 않는다). */
export function LiveBadge({ className }: { className?: string }) {
  return (
    <Badge variant="info" className={cn(className)} title="② 유사과제 확인 때 외부 자료원(ScienceON·NTIS·OpenAlex)을 바로 조회해 찾은 자료">
      실시간 검색
    </Badge>
  );
}
