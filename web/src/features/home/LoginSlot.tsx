/** 로그인 전 홈 오른쪽 열 — 레인 1 의 <LoginCard /> 자리. 그 컴포넌트가 main 에 들어오면 이 파일 안에서만 바꾼다
 *  (지금은 임시로 로그인 화면으로 가는 카드). 개인 데이터·세션이 필요한 API 는 부르지 않는다. */
import { Link } from "react-router";
import { LogIn } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Eyebrow } from "./parts";

export function LoginSlot() {
  return (
    <section aria-labelledby="login-slot-title" className="rounded-2xl border bg-card p-5" data-testid="home-login">
      <div className="flex items-baseline justify-between gap-2">
        <h2 id="login-slot-title" className="text-base font-bold">
          로그인
        </h2>
        <Eyebrow className="text-muted-foreground">Sign in</Eyebrow>
      </div>
      <p className="mt-2 text-sm text-muted-foreground">
        철도연구원 직원은 사번으로, 그 외 사용자는 아이디·비밀번호로 로그인하면 내 제안서와 건수가 여기에 보입니다.
      </p>
      <Link to="/login" state={{ from: "/" }} className={buttonVariants({ className: "mt-4 w-full" })}>
        <LogIn aria-hidden="true" />
        로그인
      </Link>
    </section>
  );
}
