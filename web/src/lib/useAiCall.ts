/** AI 버튼 호출 — 응답 시간 제한 없이 기다리고, 경과 초와 [취소]를 준다 (2026-10-28 밤, ADR 0038).
 *  취소 = fetch abort → 서버는 연결 끊김을 보고 그 작업만 멈춘다(cancel_on_disconnect). 취소하면 data·error 는
 *  그대로 두어 화면이 이전 상태로 남는다. run() 은 던지지 않는다: 결과 또는 undefined(취소·오류 — 오류는 error). */
import * as React from "react";

export interface AiCall<A, R> {
  run: (args: A) => Promise<R | undefined>;
  cancel: () => void;
  pending: boolean;
  /** 경과 초 (pending 동안 1초마다) */
  elapsed: number;
  /** 마지막 결과 (취소하면 바뀌지 않는다) */
  data: R | undefined;
  /** 마지막 오류 (취소는 오류가 아니다) */
  error: unknown;
  /** 방금 호출을 취소했다 */
  cancelled: boolean;
  reset: () => void;
}

export function isAbortError(e: unknown): boolean {
  return e instanceof DOMException ? e.name === "AbortError" : (e as { name?: string } | null)?.name === "AbortError";
}

/** pending 동안 경과 초 — React Query(useQuery 의 signal·cancelQueries)로 부르는 화면용 */
export function useElapsed(pending: boolean): number {
  const [elapsed, setElapsed] = React.useState(0);
  React.useEffect(() => {
    if (!pending) return;
    const t0 = Date.now();
    setElapsed(0);
    const id = window.setInterval(() => setElapsed(Math.floor((Date.now() - t0) / 1000)), 1000);
    return () => window.clearInterval(id);
  }, [pending]);
  return elapsed;
}

export function useAiCall<A, R>(fn: (args: A, signal: AbortSignal) => Promise<R>): AiCall<A, R> {
  const fnRef = React.useRef(fn);
  fnRef.current = fn;
  const ctrl = React.useRef<AbortController | null>(null);
  const [pending, setPending] = React.useState(false);
  const elapsed = useElapsed(pending);
  const [data, setData] = React.useState<R | undefined>(undefined);
  const [error, setError] = React.useState<unknown>(null);
  const [cancelled, setCancelled] = React.useState(false);

  // 화면을 떠나면 기다리던 호출도 끊는다
  React.useEffect(() => () => ctrl.current?.abort(), []);

  const run = React.useCallback(async (args: A): Promise<R | undefined> => {
    ctrl.current?.abort();
    const c = new AbortController();
    ctrl.current = c;
    setPending(true);
    setCancelled(false);
    setError(null);
    try {
      const out = await fnRef.current(args, c.signal);
      if (c.signal.aborted) return undefined;
      setData(out);
      return out;
    } catch (e) {
      if (c.signal.aborted || isAbortError(e)) return undefined;
      setError(e);
      return undefined;
    } finally {
      if (ctrl.current === c) {
        ctrl.current = null;
        setPending(false);
      }
    }
  }, []);

  const cancel = React.useCallback(() => {
    const c = ctrl.current;
    if (!c) return;
    ctrl.current = null;
    c.abort();
    setPending(false);
    setCancelled(true);
  }, []);

  const reset = React.useCallback(() => {
    ctrl.current?.abort();
    ctrl.current = null;
    setPending(false);
    setData(undefined);
    setError(null);
    setCancelled(false);
  }, []);

  return { run, cancel, pending, elapsed, data, error, cancelled, reset };
}
