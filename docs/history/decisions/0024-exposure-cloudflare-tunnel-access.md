# ADR 0024 — 외부 공개 시범: Cloudflare Tunnel + Cloudflare Access, 앱 로그인 이중 인증 (2026-10-27, 레인 W)

> 상태(2026-10-29 문서 최신화): 이전 계획. DNS(Gabia) 때문에 터널을 띄우지 못했고, 2026-10-28 부터 실제 공개는 Tailscale Funnel(ADR 0047).

## 배경
앱(`rra api`)·mlx 는 127.0.0.1 에만 바인딩한다(보안 G·H). 동료가 브라우저로 쓰려면 HTTPS 종단·접근 제어를 하는 역프록시가 앞에 서야
한다. 2026-10-26 비교(`docs/deploy-exposure.md` §1)는 Tailscale 을 권장했으나, 시범 대상 동료 PC 에 소프트웨어 설치·테일넷 초대를
요구하지 않는 쪽이 필요해졌다. 공개 주소는 `https://rra.ai-edu-lab.co.kr`.

## 선택지
1. Tailscale serve — 동료마다 앱 설치·초대. 도메인·DNS 불필요, 트래픽이 테일넷 밖으로 안 나감.
2. Cloudflare Tunnel + Access(이메일 OTP) — 동료는 브라우저만. 도메인이 Cloudflare DNS 여야 하고 Access 를 켜지 않으면 인터넷 공개.
3. 포트 포워딩 + 자체 TLS — 포트 개방, 보안 G 위반. 제외.

## 결정
- 시범은 2(Cloudflare Tunnel + Access). Access 가 켜진 것을 `curl -sI` 302 로 확인하기 **전**에는 터널을 올리지 않는다. Access 뒤에서도
  앱 로그인(`RRA_API_TOKEN` → 세션 쿠키)은 그대로 요구한다(이중 인증). 앱·mlx 바인딩·포트는 바꾸지 않는다.
- 앱 쪽은 설정 하나로 끝낸다: `config/api.yaml public_origin`(있으면 그 Host 로 온 로그인의 세션 쿠키 Secure + Origin 검사 허용)·
  `trust_cf_connecting_ip`(peer 가 127.0.0.1 일 때만 `CF-Connecting-IP`). `X-Forwarded-*` 는 믿지 않는다. 접속자 식별은
  `adapters/security/client_ip.py` 한 곳(레인 A 로그인 레이트리밋이 같은 함수를 쓴다). Access 사용자 이메일은 sha256 앞 12자만 로그.
- Secure 는 "public_origin 이 있으면 무조건" 이 아니라 "요청 Host 가 public_origin 의 호스트일 때"(또는 https 요청) — 터널 안은 http 라
  스킴으로 못 정하고, 127.0.0.1 직접 접속(로컬 e2e·Safari)은 Secure 쿠키를 받지 못하기 때문. Host 는 클라이언트가 정하지만 잘못 맞춰도
  쿠키가 더 엄격해질 뿐이다.
- 2026-10-27 확인: DNS 가 Gabia(`ns*.gabia.*`)라 `tunnel route dns` 가 불가하고 이 맥에 cloudflared·`~/.cloudflared` 가 없다. 그래서
  이 PR 은 코드·설정 초안·plist·절차만 넣고 터널 생성·기동·소프트웨어 설치는 하지 않는다. 기존 `agent.ai-edu-lab.co.kr`(다른 호스트)
  설정은 건드리지 않는다.
- 대체 경로: 네임서버를 Cloudflare 로 옮기지 않기로 하면 Tailscale serve(§5.5) — `public_origin` 만 `*.ts.net` 주소로 바꾸면 앱 쪽은 같다.

## 결과
- 새 파일: `src/rra/adapters/security/client_ip.py`, `config/api.yaml`, `deploy/cloudflared/config.example.yml`,
  `deploy/launchd/com.rra.tunnel.plist`, 테스트 3곳(+18).
- 운영 전 재검토 항목: 사내 자료(internal) 응답이 Cloudflare 엣지를 지난다(§1 데이터 경계). 시범 뒤 Tailscale 로 되돌릴 수 있게
  앱 설정은 출처 하나만 바꾸면 되도록 했다.
