import { useSyncExternalStore } from "react";
import { getSessionLabel, isLoggedIn, subscribeSession } from "./session";

export function useLoggedIn(): boolean {
  return useSyncExternalStore(subscribeSession, isLoggedIn, isLoggedIn);
}

/** 로그인 종류 라벨 — 상단 표시용 (직원/공용 계정/관리자). */
export function useSessionLabel(): string | null {
  return useSyncExternalStore(subscribeSession, getSessionLabel, getSessionLabel);
}
