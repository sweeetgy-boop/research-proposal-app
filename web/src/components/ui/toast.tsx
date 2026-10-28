import * as React from "react";
import { CheckCircle2, Info, TriangleAlert, X } from "lucide-react";
import { cn } from "@/lib/utils";

type ToastKind = "info" | "success" | "error";
interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
}
interface ToastApi {
  toast: (message: string, kind?: ToastKind) => void;
}

const ToastContext = React.createContext<ToastApi>({ toast: () => undefined });
let seq = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = React.useState<ToastItem[]>([]);
  const dismiss = React.useCallback((id: number) => setItems((xs) => xs.filter((x) => x.id !== id)), []);
  const toast = React.useCallback(
    (message: string, kind: ToastKind = "info") => {
      const id = ++seq;
      setItems((xs) => [...xs.slice(-3), { id, kind, message }]);
      window.setTimeout(() => dismiss(id), kind === "error" ? 8000 : 4000);
    },
    [dismiss],
  );
  const api = React.useMemo(() => ({ toast }), [toast]);
  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        className="pointer-events-none fixed inset-x-4 bottom-[calc(var(--stepnav-h)+1rem)] z-50 flex flex-col items-center gap-2 sm:inset-x-auto sm:right-4"
        role="region"
        aria-label="알림"
      >
        <div role="status" aria-live="polite" className="sr-only">
          {items.filter((i) => i.kind !== "error").map((i) => i.message).join(" ")}
        </div>
        {items.map((t) => (
          <div
            key={t.id}
            role={t.kind === "error" ? "alert" : undefined}
            className={cn(
              "pointer-events-auto flex w-full max-w-sm items-start gap-2 rounded-md border bg-card p-3 text-sm text-card-foreground shadow-lg",
              t.kind === "error" && "border-destructive/60",
              t.kind === "success" && "border-success/60",
            )}
          >
            {t.kind === "error" ? (
              <TriangleAlert className="size-4 shrink-0 text-destructive" aria-hidden="true" />
            ) : t.kind === "success" ? (
              <CheckCircle2 className="size-4 shrink-0 text-success" aria-hidden="true" />
            ) : (
              <Info className="size-4 shrink-0 text-info" aria-hidden="true" />
            )}
            <span className="flex-1">{t.message}</span>
            <button
              type="button"
              className="rounded p-0.5 text-muted-foreground hover:text-foreground"
              aria-label="알림 닫기"
              onClick={() => dismiss(t.id)}
            >
              <X className="size-4" aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  return React.useContext(ToastContext);
}
