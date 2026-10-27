/** fetch 래퍼 — 같은 출처, 세션 쿠키(httpOnly)로 인증. 상태 변경 요청에는 X-RRA-CSRF 를 붙인다.
 *  오류는 problem+json 을 ApiError 로 바꾼다. API 토큰은 어디에도 보관하지 않는다 (세션 한 번만). */
import { getCsrf, clearSession } from "@/auth/session";
import type { Problem } from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly problem: Problem;
  constructor(problem: Problem) {
    super(problem.detail || problem.title);
    this.name = "ApiError";
    this.status = problem.status;
    this.problem = problem;
  }
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError;
}

const MUTATING = new Set(["POST", "PUT", "PATCH", "DELETE"]);

async function toProblem(res: Response): Promise<Problem> {
  const fallback: Problem = {
    type: "about:blank",
    title: res.status >= 500 ? "서버 오류" : "요청 실패",
    status: res.status,
    detail: `서버가 ${res.status} 로 응답했습니다.`,
  };
  try {
    const ct = res.headers.get("content-type") ?? "";
    if (ct.includes("json")) {
      const body = (await res.json()) as Partial<Problem>;
      return {
        type: body.type ?? fallback.type,
        title: body.title ?? fallback.title,
        status: typeof body.status === "number" ? body.status : res.status,
        detail: typeof body.detail === "string" ? body.detail : fallback.detail,
      };
    }
  } catch {
    /* 본문 없음 */
  }
  return fallback;
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  /** 401 이어도 세션을 지우지 않는다 (로그인 시도 자체) */
  keepSessionOn401?: boolean;
}

export async function rawRequest(path: string, opts: RequestOptions = {}): Promise<Response> {
  const method = (opts.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = { accept: "application/json, application/problem+json" };
  if (opts.body !== undefined) headers["content-type"] = "application/json";
  if (MUTATING.has(method)) {
    const csrf = getCsrf();
    if (csrf) headers["x-rra-csrf"] = csrf;
  }
  const res = await fetch(path, {
    method,
    headers,
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    credentials: "same-origin",
    signal: opts.signal ?? null,
  });
  if (!res.ok) {
    const problem = await toProblem(res);
    if (res.status === 401 && !opts.keepSessionOn401) clearSession();
    throw new ApiError(problem);
  }
  return res;
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await rawRequest(path, opts);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
