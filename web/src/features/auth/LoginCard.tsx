import { KeyRound } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { LoginForm } from "./LoginForm";

export const LOGIN_DESCRIPTION =
  "철도연구원 직원은 사번만, 그 외 사용자는 공용 아이디와 비밀번호로 들어옵니다. 입력값은 저장하지 않고 세션 쿠키만 남깁니다 (12시간). 제안서는 연구원 서버에 저장됩니다.";

/** 로그인 카드 — 홈 오른쪽 열(로그인 전)에 놓는다. 성공하면 onSuccess (화면 이동 없음이 기본). */
export function LoginCard({
  onSuccess,
  className,
  autoFocus = false,
}: {
  onSuccess?: () => void;
  className?: string;
  autoFocus?: boolean;
}) {
  return (
    <Card className={cn("w-full", className)}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="size-5" aria-hidden="true" />
          로그인
        </CardTitle>
        <CardDescription>{LOGIN_DESCRIPTION}</CardDescription>
      </CardHeader>
      <CardContent>
        <LoginForm onSuccess={onSuccess} autoFocus={autoFocus} />
      </CardContent>
    </Card>
  );
}
