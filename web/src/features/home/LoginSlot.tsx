/** 로그인 전 홈 오른쪽 열 — 레인 1 의 <LoginCard />(화면 이동 없이 로그인, 성공하면 같은 자리가 "연구 한눈에 보기"로 바뀜).
 *  개인 데이터·세션이 필요한 API 는 부르지 않는다. */
import { LoginCard } from "@/features/auth/LoginCard";

export function LoginSlot() {
  return (
    <div data-testid="home-login">
      <LoginCard />
    </div>
  );
}
