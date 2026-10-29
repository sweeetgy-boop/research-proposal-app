import * as React from "react";
import { cn } from "@/lib/utils";

/** 영어 작은 대문자 라벨(WORKSPACE, OVERVIEW …) — 장식이라 화면 읽기 프로그램에는 숨긴다.
 *  제목·내용은 늘 한국어로 따로 쓴다. 스타일은 index.css 의 `eyebrow` 유틸리티. */
export function Eyebrow({ children, className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span aria-hidden="true" className={cn("eyebrow block", className)} {...props}>
      {children}
    </span>
  );
}
