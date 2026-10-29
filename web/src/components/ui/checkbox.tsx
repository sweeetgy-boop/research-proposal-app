import * as React from "react";
import { cn } from "@/lib/utils";

/** 네이티브 input — Radix 없이 키보드·스크린리더 동작을 브라우저에 맡긴다. */
const Checkbox = React.forwardRef<HTMLInputElement, Omit<React.InputHTMLAttributes<HTMLInputElement>, "type">>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      type="checkbox"
      className={cn("size-5 shrink-0 cursor-pointer rounded-sm border-input accent-primary disabled:cursor-not-allowed disabled:opacity-50", className)}
      {...props}
    />
  ),
);
Checkbox.displayName = "Checkbox";
export { Checkbox };
