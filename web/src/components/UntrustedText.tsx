import { cn } from "@/lib/utils";

/** 비신뢰 텍스트(수집 문서·LLM 출력)는 항상 텍스트 노드로만 그린다. HTML 해석 없음. */
export function UntrustedText({
  text,
  as: Tag = "span",
  className,
}: {
  text: string | null | undefined;
  as?: "span" | "p" | "div" | "li" | "td" | "h3";
  className?: string;
}) {
  return <Tag className={cn("whitespace-pre-wrap", className)}>{text ?? ""}</Tag>;
}
