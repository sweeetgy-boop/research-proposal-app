/** SSE(GET /v1/runs/{id}/events) 구독 — 이름 이벤트와 state 를 받는다. 끊기면 지수 백오프로
 *  다시 잇고, 끝(end) 이벤트가 오면 닫는다. 쿠키는 같은 출처라 자동으로 실린다. */
import type { RunState } from "./types";

export type NamedEvent =
  | { name: "pipeline_step"; data: { run_id: string; step: string; status: string; progress: [number, number] } }
  | { name: "draft_written"; data: { run_id: string; version: number } }
  | { name: "draft_ready"; data: { run_id: string; version: number } }
  | { name: "version_saved"; data: { run_id: string; version: number } }
  | { name: "final_review_ready"; data: { run_id: string; final_reviews: number } };

export interface SseHandlers {
  onState: (state: RunState) => void;
  onEvent?: (ev: NamedEvent) => void;
  onEnd?: (status: string) => void;
  onError?: (attempt: number) => void;
}

const NAMES: NamedEvent["name"][] = [
  "pipeline_step",
  "draft_written",
  "draft_ready",
  "version_saved",
  "final_review_ready",
];

export function subscribeRunEvents(runId: string, handlers: SseHandlers): () => void {
  let es: EventSource | null = null;
  let attempt = 0;
  let closed = false;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const open = () => {
    if (closed) return;
    es = new EventSource(`/v1/runs/${encodeURIComponent(runId)}/events`);
    es.addEventListener("state", (e) => {
      attempt = 0;
      try {
        handlers.onState(JSON.parse((e as MessageEvent).data) as RunState);
      } catch {
        /* 깨진 이벤트는 무시 */
      }
    });
    for (const name of NAMES) {
      es.addEventListener(name, (e) => {
        try {
          handlers.onEvent?.({ name, data: JSON.parse((e as MessageEvent).data) } as NamedEvent);
        } catch {
          /* ignore */
        }
      });
    }
    es.addEventListener("end", (e) => {
      let status = "unknown";
      try {
        status = (JSON.parse((e as MessageEvent).data) as { status: string }).status;
      } catch {
        /* ignore */
      }
      closed = true;
      es?.close();
      handlers.onEnd?.(status);
    });
    es.onerror = () => {
      if (closed) return;
      es?.close();
      attempt += 1;
      handlers.onError?.(attempt);
      const delay = Math.min(30_000, 1000 * 2 ** Math.min(attempt, 5));
      timer = setTimeout(open, delay);
    };
  };
  open();
  return () => {
    closed = true;
    if (timer) clearTimeout(timer);
    es?.close();
  };
}
