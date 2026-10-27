import * as React from "react";
import { useLocation, useNavigate } from "react-router";
import { KeyRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TabPanel, Tabs } from "@/components/ui/tabs";
import { ProblemBanner } from "@/components/ProblemBanner";
import { login } from "@/api/endpoints";
import type { SessionIn } from "@/api/types";
import { useLoggedIn } from "@/auth/useSession";

type Tab = "staff" | "guest";
const TABS = [
  { id: "staff", label: "철도연구원 직원(사번)" },
  { id: "guest", label: "그 외 사용자(아이디·비밀번호)" },
];

/** 로그인 — 직원은 사번만, 그 외 사용자는 공용 아이디·비밀번호. 관리자 토큰은 작은 링크 아래.
 *  입력값은 요청 본문으로만 보내고 성공·실패 뒤 메모리에서도 지운다 (세션에는 CSRF 와 종류만). */
export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const loggedIn = useLoggedIn();
  const [tab, setTab] = React.useState<Tab>("staff");
  const [staffNo, setStaffNo] = React.useState("");
  const [guestId, setGuestId] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [token, setToken] = React.useState("");
  const [admin, setAdmin] = React.useState(false);
  const [error, setError] = React.useState<unknown>(null);
  const [busy, setBusy] = React.useState(false);
  const from = (location.state as { from?: string } | null)?.from ?? "/new";

  React.useEffect(() => {
    if (loggedIn) navigate(from, { replace: true });
  }, [loggedIn, from, navigate]);

  const canSubmit = admin
    ? token.trim().length > 0
    : tab === "staff"
      ? staffNo.trim().length > 0
      : guestId.trim().length > 0 && password.length > 0;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    const body: SessionIn = admin
      ? { kind: "token", token: token.trim() }
      : tab === "staff"
        ? { kind: "staff", staff_no: staffNo.trim() }
        : { kind: "guest", id: guestId.trim(), password };
    setBusy(true);
    setError(null);
    try {
      await login(body);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      // 입력값은 성공·실패 모두 메모리에서 지운다
      setStaffNo("");
      setPassword("");
      setToken("");
      setBusy(false);
    }
  };

  const switchTab = (id: string) => {
    setTab(id as Tab);
    setError(null);
  };

  return (
    <div className="mx-auto max-w-md">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound className="size-5" aria-hidden="true" />
            로그인
          </CardTitle>
          <CardDescription>
            철도연구원 직원은 사번만, 그 외 사용자는 공용 아이디와 비밀번호로 들어옵니다. 입력값은 저장하지 않고
            세션 쿠키만 남깁니다 (12시간).
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!admin && <Tabs items={TABS} value={tab} onChange={switchTab} label="로그인 종류" />}
          <form onSubmit={submit} className="space-y-4" noValidate>
            {admin ? (
              <div className="space-y-2 pt-4">
                <Label htmlFor="token">관리자 접속 토큰</Label>
                <Input
                  id="token"
                  type="password"
                  autoComplete="off"
                  autoFocus
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  required
                  aria-invalid={error ? true : undefined}
                  aria-describedby={error ? "login-error" : undefined}
                />
              </div>
            ) : (
              <>
                <TabPanel id="staff" active={tab === "staff"}>
                  <div className="space-y-2">
                    <Label htmlFor="staff-no">사번</Label>
                    <Input
                      id="staff-no"
                      type="password"
                      inputMode="text"
                      autoComplete="off"
                      autoFocus
                      value={staffNo}
                      onChange={(e) => setStaffNo(e.target.value)}
                      required
                      aria-invalid={error ? true : undefined}
                      aria-describedby={error ? "login-error" : "staff-hint"}
                    />
                    <p id="staff-hint" className="text-xs text-muted-foreground">
                      등록된 사번만 통과합니다. 사번은 화면·기록 어디에도 남지 않습니다.
                    </p>
                  </div>
                </TabPanel>
                <TabPanel id="guest" active={tab === "guest"}>
                  <div className="space-y-4">
                    <div className="space-y-2">
                      <Label htmlFor="guest-id">아이디</Label>
                      <Input
                        id="guest-id"
                        type="text"
                        autoComplete="username"
                        autoFocus
                        value={guestId}
                        onChange={(e) => setGuestId(e.target.value)}
                        required
                        aria-invalid={error ? true : undefined}
                        aria-describedby={error ? "login-error" : undefined}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="guest-password">비밀번호</Label>
                      <Input
                        id="guest-password"
                        type="password"
                        autoComplete="current-password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                        aria-invalid={error ? true : undefined}
                        aria-describedby={error ? "login-error" : undefined}
                      />
                    </div>
                  </div>
                </TabPanel>
              </>
            )}
            <div id="login-error" className="min-h-6">
              <ProblemBanner error={error} />
            </div>
            <Button type="submit" className="w-full" disabled={busy || !canSubmit}>
              {busy ? "확인 중…" : "로그인"}
            </Button>
          </form>
          <p className="mt-4 text-right text-xs">
            <button
              type="button"
              className="text-muted-foreground underline-offset-2 hover:underline"
              aria-expanded={admin}
              onClick={() => {
                setAdmin((v) => !v);
                setError(null);
              }}
            >
              {admin ? "직원·일반 사용자로 돌아가기" : "관리자"}
            </button>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
