import * as React from "react";
import { useLocation, useNavigate } from "react-router";
import { Dialog } from "@/components/ui/dialog";
import { logout } from "@/api/endpoints";
import { isLoggedIn } from "@/auth/session";
import { useLoggedIn } from "@/auth/useSession";
import { LOGIN_DESCRIPTION } from "./LoginCard";
import { LoginForm } from "./LoginForm";
import { LoginDialogContext, type LoginNext } from "./loginContext";

/** 로그인 창 — 지금 화면 위에 띄운다. 닫아도 화면은 그대로. */
export function LoginDialog({ open, onClose, onSuccess }: { open: boolean; onClose: () => void; onSuccess?: () => void }) {
  return (
    <Dialog open={open} onClose={onClose} title="로그인" description={LOGIN_DESCRIPTION}>
      {open && <LoginForm onSuccess={onSuccess} />}
    </Dialog>
  );
}

/** 화면 틀(Layout) 안에 둔다. 로그인 창 하나를 앱 전체가 함께 쓴다.
 *  주소 상태 `{ login: true }`(옛 /login 주소에서 넘어옴)이면 창을 연다. */
export function LoginDialogProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setOpen] = React.useState(false);
  const nextRef = React.useRef<LoginNext>(undefined);
  const navigate = useNavigate();
  const location = useLocation();
  const loggedIn = useLoggedIn();

  const open = React.useCallback((next?: LoginNext) => {
    nextRef.current = next;
    setOpen(true);
  }, []);
  // 로그인 성공으로 창이 닫힐 때(브라우저 close 이벤트)는 이어 갈 곳을 지우지 않는다 — onSuccess 가 쓴다
  const close = React.useCallback(() => {
    if (!isLoggedIn()) nextRef.current = undefined;
    setOpen(false);
  }, []);

  const loggingOut = React.useRef(false);
  const logoutTo = React.useCallback(
    async (path = "/") => {
      loggingOut.current = true;
      nextRef.current = undefined;
      setOpen(false);
      try {
        await logout();
      } finally {
        navigate(path, { replace: true });
        setTimeout(() => {
          loggingOut.current = false;
        }, 0);
      }
    },
    [navigate],
  );
  const isLoggingOut = React.useCallback(() => loggingOut.current, []);

  const wantsLogin = (location.state as { login?: boolean } | null)?.login === true;
  React.useEffect(() => {
    if (!wantsLogin) return;
    navigate(location.pathname + location.search, { replace: true, state: null });
    if (!loggedIn) open();
  }, [wantsLogin, loggedIn, location.pathname, location.search, navigate, open]);

  const onSuccess = () => {
    const next = nextRef.current;
    nextRef.current = undefined;
    setOpen(false);
    if (typeof next === "string") navigate(next);
    else if (typeof next === "function") next();
  };

  const value = React.useMemo(
    () => ({ open, close, isOpen, logoutTo, isLoggingOut }),
    [open, close, isOpen, logoutTo, isLoggingOut],
  );
  return (
    <LoginDialogContext.Provider value={value}>
      {children}
      <LoginDialog open={isOpen && !loggedIn} onClose={close} onSuccess={onSuccess} />
    </LoginDialogContext.Provider>
  );
}
