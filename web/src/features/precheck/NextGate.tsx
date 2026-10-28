import { Button } from "@/components/ui/button";

/** "다음" 버튼 — 막혀 있으면 옆에 이유를 보인다 (예: 차단 경보를 확인해 주세요). */
export function NextGate({ label, reason, onNext }: { label: string; reason: string | null; onNext: () => void }) {
  const blocked = !!reason;
  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      {blocked && (
        <p id="next-reason" role="status" className="text-sm text-destructive">
          {reason}
        </p>
      )}
      <Button onClick={onNext} disabled={blocked} aria-disabled={blocked} aria-describedby={blocked ? "next-reason" : undefined}>
        {label}
      </Button>
    </div>
  );
}
