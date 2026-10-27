import * as React from "react";
import { useLocation, useNavigate } from "react-router";
import { KeyRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ProblemBanner } from "@/components/ProblemBanner";
import { login } from "@/api/endpoints";
import { useLoggedIn } from "@/auth/useSession";

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const loggedIn = useLoggedIn();
  const [token, setToken] = React.useState("");
  const [error, setError] = React.useState<unknown>(null);
  const [busy, setBusy] = React.useState(false);
  const from = (location.state as { from?: string } | null)?.from ?? "/new";

  React.useEffect(() => {
    if (loggedIn) navigate(from, { replace: true });
  }, [loggedIn, from, navigate]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await login(token.trim());
      setToken(""); // 토큰은 메모리에서도 지운다
      navigate(from, { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
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
            관리자가 준 접속 토큰을 한 번 입력합니다. 토큰은 저장하지 않고 세션 쿠키만 남깁니다 (12시간).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4" noValidate>
            <div className="space-y-2">
              <Label htmlFor="token">접속 토큰</Label>
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
            <div id="login-error" className="min-h-6">
              <ProblemBanner error={error} />
            </div>
            <Button type="submit" className="w-full" disabled={busy || !token.trim()}>
              {busy ? "확인 중…" : "로그인"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
