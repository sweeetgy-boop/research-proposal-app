import * as React from "react";
import { Outlet } from "react-router";
import { LockKeyhole } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LoginCard } from "@/features/auth/LoginCard";
import { useLoginDialog } from "@/features/auth/loginContext";
import { useLoggedIn } from "./useSession";

/** 로그인이 필요한 화면 — 로그인 전이면 주소는 그대로 두고 그 자리에 로그인 창을 띄운다.
 *  로그인하면 같은 주소의 화면이 그대로 그려진다(원래 가려던 곳으로 이어짐). 로그인 전에는 화면 내용을
 *  그리지 않으므로 API 도 부르지 않는다. */
export function RequireAuth() {
  const loggedIn = useLoggedIn();
  if (!loggedIn) return <LoginGate />;
  return <Outlet />;
}

function LoginGate() {
  const dialog = useLoginDialog();
  const opened = React.useRef(false);
  React.useEffect(() => {
    if (!dialog || opened.current || dialog.isLoggingOut()) return;
    opened.current = true;
    dialog.open();
  }, [dialog]);

  // 창 제공자가 없으면(단위 테스트 등) 카드를 그 자리에 그린다
  if (!dialog) {
    return (
      <div className="mx-auto max-w-md">
        <LoginCard autoFocus />
      </div>
    );
  }
  return (
    <section aria-labelledby="login-gate-title" className="mx-auto max-w-md py-10 text-center">
      <LockKeyhole className="mx-auto size-8 text-muted-foreground" aria-hidden="true" />
      <h1 id="login-gate-title" className="mt-3 text-lg font-semibold">
        로그인이 필요한 화면입니다
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">로그인하면 이 화면으로 바로 이어집니다.</p>
      <Button className="mt-4" onClick={() => dialog.open()}>
        로그인 창 열기
      </Button>
    </section>
  );
}
