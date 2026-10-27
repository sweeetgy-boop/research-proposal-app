/** 세션 상태 — CSRF 토큰만 sessionStorage 에 둔다(새로고침 유지). API 토큰은 절대 저장하지 않는다.
 *  세션 쿠키(rra_session)는 httpOnly 라 JS 가 볼 수 없고, 만료는 401 로 안다. */
const KEY = "rra-csrf";
type Listener = () => void;
const listeners = new Set<Listener>();
let csrf: string | null = readStored();

function readStored(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

function emit() {
  for (const l of listeners) l();
}

export function getCsrf(): string | null {
  return csrf;
}

export function isLoggedIn(): boolean {
  return csrf !== null;
}

export function setSession(token: string): void {
  csrf = token;
  try {
    sessionStorage.setItem(KEY, token);
  } catch {
    /* 저장소 없음 — 메모리만 */
  }
  emit();
}

export function clearSession(): void {
  csrf = null;
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
  emit();
}

export function subscribeSession(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
