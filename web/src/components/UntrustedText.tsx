import { cn } from "@/lib/utils";

/** 비신뢰 텍스트(수집 문서·LLM 출력)는 항상 텍스트 노드로만 그린다. HTML 해석 없음. */
export function UntrustedText({
  text,
  as: Tag = "span",
  className,
  onClick,
}: {
  text: string | null | undefined;
  as?: "span" | "p" | "div" | "li" | "td" | "h3";
  className?: string;
  /** 보조 클릭(같은 동작의 진짜 버튼이 옆에 있어야 한다 — 키보드 사용자는 그 버튼으로) */
  onClick?: () => void;
}) {
  return (
    <Tag className={cn("whitespace-pre-wrap", className)} onClick={onClick}>
      {text ?? ""}
    </Tag>
  );
}
