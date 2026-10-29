import * as React from "react";

/** 로그인 뒤 이어 갈 곳 — 주소(문자열)면 그리로 이동, 함수면 실행, 없으면 지금 화면에 머문다. */
export type LoginNext = string | (() => void) | undefined;

export interface LoginDialogApi {
  open: (next?: LoginNext) => void;
  close: () => void;
  isOpen: boolean;
  /** 로그아웃 → path(기본 홈). 로그아웃 중에는 로그인 창을 저절로 띄우지 않는다. */
  logoutTo: (path?: string) => Promise<void>;
  /** 로그아웃 중이면 true — RequireAuth 가 창을 저절로 열지 않게 */
  isLoggingOut: () => boolean;
}

export const LoginDialogContext = React.createContext<LoginDialogApi | null>(null);

export function useLoginDialog(): LoginDialogApi | null {
  return React.useContext(LoginDialogContext);
}
