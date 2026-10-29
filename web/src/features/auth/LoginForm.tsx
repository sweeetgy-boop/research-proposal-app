import * as React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TabPanel, Tabs } from "@/components/ui/tabs";
import { ProblemBanner } from "@/components/ProblemBanner";
import { login } from "@/api/endpoints";
import type { SessionIn } from "@/api/types";

type Tab = "staff" | "guest";

/** 로그인 입력 — 직원은 사번만, 그 외 사용자는 공용 아이디·비밀번호, 관리자 토큰은 작은 링크 아래.
 *  입력값은 요청 본문으로만 보내고 성공·실패 뒤 메모리에서도 지운다 (세션에는 CSRF 와 종류만).
 *  카드(LoginCard)와 창(LoginDialog)이 함께 쓴다. 한 화면에 둘이 같이 있어도 id 가 겹치지 않게 useId 를 붙인다. */
export function LoginForm({ onSuccess, autoFocus = true }: { onSuccess?: () => void; autoFocus?: boolean }) {
  const uid = React.useId().replace(/[^A-Za-z0-9_-]/g, "");
  const staffTab = `${uid}-staff`;
  const guestTab = `${uid}-guest`;
  const tabs = React.useMemo(
    () => [
      { id: staffTab, label: "철도연구원 직원(사번)" },
      { id: guestTab, label: "그 외 사용자(아이디·비밀번호)" },
    ],
    [staffTab, guestTab],
  );
  const [tab, setTab] = React.useState<Tab>("staff");
  const [staffNo, setStaffNo] = React.useState("");
  const [guestId, setGuestId] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [token, setToken] = React.useState("");
  const [admin, setAdmin] = React.useState(false);
  const [error, setError] = React.useState<unknown>(null);
  const [busy, setBusy] = React.useState(false);
  const errId = `${uid}-error`;
  const hintId = `${uid}-staff-hint`;
  const describedBy = error ? errId : undefined;
  const rootRef = React.useRef<HTMLDivElement>(null);

  // 창(showModal)은 자식이 그려진 뒤 열리며 포커스를 옮기므로, 한 박자 늦게 첫 입력 칸으로 포커스
  React.useEffect(() => {
    if (!autoFocus) return;
    const t = setTimeout(() => rootRef.current?.querySelector<HTMLInputElement>("form input")?.focus(), 0);
    return () => clearTimeout(t);
  }, [autoFocus]);

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
    let ok = false;
    try {
      await login(body);
      ok = true;
    } catch (err) {
      setError(err);
    } finally {
      // 입력값은 성공·실패 모두 메모리에서 지운다
      setStaffNo("");
      setPassword("");
      setToken("");
      setBusy(false);
    }
    if (ok) onSuccess?.();
  };

  const switchTab = (id: string) => {
    setTab(id === staffTab ? "staff" : "guest");
    setError(null);
  };

  return (
    <div ref={rootRef}>
      {!admin && <Tabs items={tabs} value={tab === "staff" ? staffTab : guestTab} onChange={switchTab} label="로그인 종류" />}
      <form onSubmit={submit} className="space-y-4" noValidate>
        {admin ? (
          <div className="space-y-2 pt-4">
            <Label htmlFor={`${uid}-token`}>관리자 접속 토큰</Label>
            <Input
              id={`${uid}-token`}
              type="password"
              autoComplete="off"
              autoFocus={autoFocus}
              value={token}
              onChange={(e) => setToken(e.target.value)}
              required
              aria-invalid={error ? true : undefined}
              aria-describedby={describedBy}
            />
          </div>
        ) : (
          <>
            <TabPanel id={staffTab} active={tab === "staff"}>
              <div className="space-y-2">
                <Label htmlFor={`${uid}-staff-no`}>사번</Label>
                <Input
                  id={`${uid}-staff-no`}
                  type="password"
                  inputMode="text"
                  autoComplete="off"
                  autoFocus={autoFocus}
                  value={staffNo}
                  onChange={(e) => setStaffNo(e.target.value)}
                  required
                  aria-invalid={error ? true : undefined}
                  aria-describedby={error ? errId : hintId}
                />
                <p id={hintId} className="text-xs text-muted-foreground">
                  등록된 사번만 통과합니다. 사번은 화면·기록 어디에도 남지 않습니다.
                </p>
              </div>
            </TabPanel>
            <TabPanel id={guestTab} active={tab === "guest"}>
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor={`${uid}-guest-id`}>아이디</Label>
                  <Input
                    id={`${uid}-guest-id`}
                    type="text"
                    autoComplete="username"
                    autoFocus={autoFocus}
                    value={guestId}
                    onChange={(e) => setGuestId(e.target.value)}
                    required
                    aria-invalid={error ? true : undefined}
                    aria-describedby={describedBy}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor={`${uid}-guest-password`}>비밀번호</Label>
                  <Input
                    id={`${uid}-guest-password`}
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    aria-invalid={error ? true : undefined}
                    aria-describedby={describedBy}
                  />
                </div>
                <p className="text-xs text-muted-foreground">공용 계정의 제안서는 함께 쓰는 사람에게 보입니다.</p>
              </div>
            </TabPanel>
          </>
        )}
        <div id={errId} className="min-h-6">
          <ProblemBanner error={error} />
        </div>
        <Button type="submit" className="w-full" disabled={busy || !canSubmit}>
          {busy ? "확인 중…" : "로그인"}
        </Button>
      </form>
      <p className="mt-4 text-right text-xs">
        <button
          type="button"
          className="min-h-6 text-muted-foreground underline-offset-2 hover:underline"
          aria-expanded={admin}
          onClick={() => {
            setAdmin((v) => !v);
            setError(null);
          }}
        >
          {admin ? "직원·일반 사용자로 돌아가기" : "관리자"}
        </button>
      </p>
    </div>
  );
}
