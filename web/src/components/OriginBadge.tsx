import { Badge } from "@/components/ui/badge";
import { ORIGIN_LABELS } from "@/lib/sections";
import { cn } from "@/lib/utils";

const COLOR: Record<string, string> = {
  "AI 작성": "border-origin-local text-origin-local",
  "Argon 보완": "border-origin-argon text-origin-argon",
  "Argon 추가": "border-origin-added text-origin-added",
  "제안자 수정": "border-origin-edit text-origin-edit",
  "제안자 입력": "border-origin-edit text-origin-edit",
  "앱 규칙": "border-origin-local text-origin-local",
};

export function OriginBadge({ origin, className }: { origin: string; className?: string }) {
  const label = ORIGIN_LABELS[origin] ?? origin;
  return (
    <Badge variant="outline" className={cn("font-medium", COLOR[label], className)} title={`문장 출처: ${label}`}>
      {label}
    </Badge>
  );
}
