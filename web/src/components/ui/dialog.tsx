import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "./button";

/** 네이티브 <dialog>.showModal() — 포커스 가두기·Esc 닫기·배경 inert 를 브라우저가 처리한다.
 *  (Radix 는 <style> 을 주입해 CSP style-src 'self' 와 맞지 않아 쓰지 않는다.) */
export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
  /** 바깥 클릭·Esc 로 닫지 못하게 */
  modalOnly?: boolean;
}

export function Dialog({ open, onClose, title, description, children, footer, className, modalOnly }: DialogProps) {
  const ref = React.useRef<HTMLDialogElement>(null);
  const titleId = React.useId();
  const descId = React.useId();

  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    else if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      aria-describedby={description ? descId : undefined}
      className={cn(
        "m-auto w-[min(92vw,36rem)] rounded-lg border bg-card p-0 text-card-foreground shadow-xl open:flex open:flex-col",
        className,
      )}
      onCancel={(e) => {
        e.preventDefault();
        if (!modalOnly) onClose();
      }}
      onClose={onClose}
      onClick={(e) => {
        if (modalOnly) return;
        if (e.target === ref.current) onClose(); // 배경 클릭
      }}
    >
      <div className="flex items-start justify-between gap-4 border-b p-4 sm:p-5">
        <div>
          <h2 id={titleId} className="text-lg font-semibold leading-tight">
            {title}
          </h2>
          {description && (
            <p id={descId} className="mt-1 text-sm text-muted-foreground">
              {description}
            </p>
          )}
        </div>
        {!modalOnly && (
          <Button variant="ghost" size="icon" aria-label="닫기" onClick={onClose}>
            <X aria-hidden="true" />
          </Button>
        )}
      </div>
      <div className="max-h-[60vh] overflow-y-auto p-4 sm:p-5">{children}</div>
      {footer && <div className="flex flex-wrap justify-end gap-2 border-t p-4 sm:p-5">{footer}</div>}
    </dialog>
  );
}
