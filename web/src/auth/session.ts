/** 세션 상태 — CSRF 토큰과 로그인 종류(직원/공용 계정/관리자 라벨)만 sessionStorage 에 둔다(새로고침
 *  유지). API 토큰·사번·비밀번호는 절대 저장하지 않는다. 세션 쿠키(rra_session)는 httpOnly 라 JS 가
 *  볼 수 없고, 만료는 401 로 안다. */
const KEY = "rra-csrf";
const KIND_KEY = "rra-session-kind";
type Listener = () => void;
const listeners = new Set<Listener>();
let csrf: string | null = readStored(KEY);
let kindLabel: string | null = readStored(KIND_KEY);

function readStored(key: string): string | null {
  try {
    return sessionStorage.getItem(key);
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

/** 상단에 보일 로그인 종류 라벨 ("직원" | "공용 계정" | "관리자"). 사번은 절대 오지 않는다. */
export function getSessionLabel(): string | null {
  return kindLabel;
}

export function setSession(token: string, kind?: string, label?: string): void {
  csrf = token;
  kindLabel = label ?? (kind ?? null);
  try {
    sessionStorage.setItem(KEY, token);
    if (kindLabel) sessionStorage.setItem(KIND_KEY, kindLabel);
    else sessionStorage.removeItem(KIND_KEY);
  } catch {
    /* 저장소 없음 — 메모리만 */
  }
  emit();
}

export function clearSession(): void {
  csrf = null;
  kindLabel = null;
  try {
    sessionStorage.removeItem(KEY);
    sessionStorage.removeItem(KIND_KEY);
  } catch {
    /* ignore */
  }
  emit();
}

export function subscribeSession(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
