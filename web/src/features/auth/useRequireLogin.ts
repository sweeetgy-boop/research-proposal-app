import * as React from "react";
import { useNavigate } from "react-router";
import { isLoggedIn } from "@/auth/session";
import { useLoginDialog, type LoginNext } from "./loginContext";

/** 로그인이 필요한 동작 — 로그인돼 있으면 바로 이어 가고, 아니면 그 자리에 로그인 창을 띄운 뒤
 *  로그인하면 이어 간다. `requireLogin("/new")` 또는 `requireLogin(() => setOpen(true))`.
 *  창 제공자(LoginDialogProvider)가 없는 곳(단위 테스트)에서는 홈으로 보내며 창을 연다. */
export function useRequireLogin(): (next?: LoginNext) => void {
  const dialog = useLoginDialog();
  const navigate = useNavigate();
  return React.useCallback(
    (next?: LoginNext) => {
      if (isLoggedIn()) {
        if (typeof next === "string") navigate(next);
        else if (typeof next === "function") next();
        return;
      }
      if (dialog) dialog.open(next);
      else navigate("/", { state: { login: true } });
    },
    [dialog, navigate],
  );
}
