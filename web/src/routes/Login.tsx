import { Navigate, useLocation } from "react-router";
import { useLoggedIn } from "@/auth/useSession";

/** 옛 /login 주소 — 로그인 페이지는 따로 없다. 홈으로 보내며 로그인 창을 연다(Layout 의 LoginDialogProvider).
 *  이미 로그인돼 있으면 원래 가려던 곳(state.from) 또는 홈으로. */
export default function Login() {
  const loggedIn = useLoggedIn();
  const from = (useLocation().state as { from?: string } | null)?.from;
  if (loggedIn) return <Navigate to={from ?? "/"} replace />;
  return <Navigate to="/" replace state={{ login: true }} />;
}
