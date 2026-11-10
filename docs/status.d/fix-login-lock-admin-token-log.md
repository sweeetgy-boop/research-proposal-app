# fix/login-lock-admin-token-log (2026-11-10) 전달 사항

## 전달한 것
- **관리 토큰 시도 제한** 세션 로그인 `kind=token` 과 헤더 토큰(`X-RRA-Token`·Bearer) 실패를 접속자 IP 창(`auth.yaml lockout.ip_failures`·`ip_window_sec`)에
  사번·공용 계정 실패와 함께 센다. 넘으면 그 IP 는 맞는 토큰도 401(문구 그대로). 계정 키로는 세지 않고, 접속자 IP 를 모르면(127.0.0.1) IP 잠금이 없다.
  규칙은 `usecases/login.Login.token`, 미들웨어는 조립(`api_middlewares(guard=login.guard)`)이 넘긴 같은 `LoginGuard` 를 쓴다.
- **잠금 로그** `rra.api.auth` WARNING — `api.login.locked kind= scope= ip= seconds=`(시작), `api.login.blocked`(잠긴 뒤 시도), `api.login.slowdown failures= delay=`.
  문장은 `domain/rules/auth_policy.lock_log_lines`(종류·범위·IP·초만 받는다). `rra api` 로그 설정에서 걸러지지 않음을 시험으로 고정.
- **변하지 않은 것** 응답 문구·상태 코드, 설정 키, 세션 쿠키 요청, `login` 없는 조립(토큰 비교만).

## 남은 것
- 여러 IP 로 나눈 시도는 전체 지연(2초)만 걸린다. 기록은 메모리라 API 재시작 때 초기화된다.
- 헤더 토큰 실패에는 전체 지연(잠)을 걸지 않는다(실패 수에는 더해져 로그인 지연에는 반영).
- 잠긴 동안의 시도도 실패로 세므로(종전 동작) 계속 시도하면 잠금이 이어진다.
