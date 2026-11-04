import { useSyncExternalStore } from "react";
import { getSessionLabel, getSessionRole, isLoggedIn, subscribeSession } from "./session";

export function useLoggedIn(): boolean {
  return useSyncExternalStore(subscribeSession, isLoggedIn, isLoggedIn);
}

/** 로그인 종류 라벨 — 상단 표시용 (직원/공용 계정/관리자). */
export function useSessionLabel(): string | null {
  return useSyncExternalStore(subscribeSession, getSessionLabel, getSessionLabel);
}

/** 관리자(토큰 로그인)인지 — 관리자 전용 안내(예: Argon 연결 오류 사유)를 가릴 때만. */
export function useIsAdmin(): boolean {
  return useSyncExternalStore(subscribeSession, getSessionRole, getSessionRole) === "admin";
}
