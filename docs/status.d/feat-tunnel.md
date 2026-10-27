# 레인 W — feat/tunnel (2026-10-27, 브라우저 접속: Cloudflare Tunnel + Access 준비) 전달 사항

## 현황 행 (docs/status.md 용)
| 2026-10-27 | 레인 W 브라우저 접속 | 앱 조정 완료(`config/api.yaml`·쿠키 Secure·Origin 검사·`client_ip`·이메일 해시 로그), 터널 설정 초안·plist·절차 완료. **터널 미기동·Access 미확인** — DNS 가 Gabia, cloudflared 미설치. 사람 작업 6단계 대기 | PR #TBD |

## 사전 확인 결과 (2026-10-27 17:30, 이 맥, 값은 기록만)
- `dig +short NS ai-edu-lab.co.kr` → `ns1.gabia.co.kr`·`ns.gabia.co.kr`·`ns.gabia.net` — **Cloudflare 가 아님**(통합 담당 17:25 확인과 같음).
- `dig +short rra.ai-edu-lab.co.kr` → 없음(레코드 없음). `agent.ai-edu-lab.co.kr` → `34.64.53.121`(다른 호스트, 이 맥의 터널 아님 —
  어떤 설정도 바꾸지 않았다).
- `~/.cloudflared` 없음(cert.pem·config.yml 없음). `cloudflared`·`tailscale` 실행 파일 없음(`command -v` 둘 다 없음, /Applications 에도 없음).
  launchd 에 cloudflare·tailscale 항목 0, `~/Library/LaunchAgents` 에 com.rra.* 0 (이 개발기에는 서비스 미등록). `brew` 는 있음.
- 결론: 규칙 3·5 대로 터널을 만들거나 올리지 않았다. 소프트웨어 설치 없음. 네트워크로 나간 것은 `dig` 조회뿐.

## 납품 목록
- **설정** `config/api.yaml`: `public_origin: https://rra.ai-edu-lab.co.kr`, `trust_cf_connecting_ip: false`(터널 기동 뒤 true 로).
  `config_loader.api_config(settings)` — 파일 없으면 `""`/`False`, 모르는 키·`https://host` 아닌 값·bool 아닌 값은 ValueError. `.env` 변경 없음.
- **조립** `composition.api_middlewares` 가 `TokenAuthMiddleware(public_origin=…, trust_cf=…)`, `build_api` 가 `create_app(public_origin=…)`.
- **세션 쿠키** `POST /v1/session`: Secure = https 요청 **또는** 요청 Host == public_origin 호스트(터널 안은 http). 127.0.0.1 직접 접속은 그대로.
- **Origin 검사**(`adapters/security/middleware.origin_allowed`): 쿠키 인증의 POST/PUT/PATCH/DELETE 와 로그인(POST /v1/session)에서 Origin 이
  있으면 public_origin 또는 같은 Host 의 http/https 만 허용, `null`·타 출처는 403 `허용되지 않은 출처(Origin)입니다.` Origin 없는 요청·GET·
  헤더 토큰 인증은 영향 없음(기존 CSRF 규칙 유지).
- **접속자 식별** `src/rra/adapters/security/client_ip.py` — `client_ip(request, trust_cf: bool) -> str`(Starlette Request 또는 ASGI scope;
  trust_cf 이고 peer 127.0.0.1 일 때만 `CF-Connecting-IP`, IP 형식 아니면 peer; `X-Forwarded-*` 무시), `access_user_hash(request) -> str | None`
  (`Cf-Access-Authenticated-User-Email` 소문자·공백 제거 → sha256 앞 12자). `rra.adapters.security` 에서 export. **레인 A 는 이 서명을 그대로
  import** — 바꾸지 않았다. 미들웨어는 보호 경로마다 `scope["state"]["rra_client_ip"]`·`["rra_access_user"]` 를 채운다(레이트리밋 키로 쓸 것).
- **로그** 거부(401/403) 때만 `rra.api.auth` INFO: `api.auth.reject status= method= path= ip= access_user=<해시 12자>`. 이메일 원문 없음.
  기존에 접속자 IP 를 쓰는 곳(레이트리밋·접근 로그)은 없었다(uvicorn access_log=False) — 바꿀 사용처 없음.
- **터널 파일** `deploy/cloudflared/config.example.yml`(tunnel/credentials-file 자리표시자 `<TUNNEL_ID>`, ingress rra.ai-edu-lab.co.kr →
  http://127.0.0.1:8000, 마지막 http_status:404), `deploy/launchd/com.rra.tunnel.plist`(`/opt/homebrew/bin/cloudflared tunnel --config
  /Users/chan/.cloudflared/config.yml --no-autoupdate run rra`, KeepAlive, 로그 `~/Library/Logs/rra-tunnel*.log`, 비밀 없음).
- **문서** `docs/deploy-exposure.md` §5(결정·이유·막힌 점·앱 쪽·터널 절차·기존 터널 절차·Access 확인·Tailscale 대체), `deploy/README.md`
  §0·§2(표+명령)·§3(curl)·§6, ADR `docs/history/decisions/0024-exposure-cloudflare-tunnel-access.md`.
- **테스트 +18** `tests/adapters/test_client_ip.py`(IP 네 경우 parametrize·비IP/X-Forwarded 무시·Request 객체·해시), `tests/entrypoints/
  test_api_public_origin.py`(쿠키 Secure 3경우·public_origin 없음·Origin 허용/거부·로그인 Origin·거부 로그 해시/peer·api_config 기본값/
  정규화/검증·저장소 api.yaml 값과 미들웨어 연결), `tests/deploy/test_launchd_plists.py`(tunnel plist·config.example.yml, PLISTS 5종).
  `pytest -q -n auto` 1,696 통과·16 skip, `lint-imports` 8 kept, `ruff check src tests` 통과. 프론트엔드 영향 없음(openapi 변경 없음).

## [자동 진행] 판단
1. Secure 를 "public_origin 이 있으면 무조건" 이 아니라 "요청 Host 가 public_origin 호스트일 때(또는 https)" 로 했다 — 지시 문구보다 좁지만
   터널 경유 요청은 전부 해당하고, 127.0.0.1 로컬 e2e·Safari 가 Secure 쿠키를 거부하는 문제를 피한다. 더 넓히려면 `app.py` 의 한 줄
   (`secure=…`) 만 바꾸면 된다.
2. Origin 검사는 기존에 없던 것이라 추가하되 **Origin 헤더가 있을 때만** 적용(curl·구형 클라이언트·기존 테스트 영향 없음). 로그인 POST 에도 적용.
3. `trust_cf_connecting_ip` 저장소 기본값은 false — 터널 없이 돌 때 127.0.0.1 의 아무 클라이언트가 헤더로 IP 를 꾸밀 수 있어서. 터널 기동 뒤 true.
4. `client_ip` 의 루프백 판정은 지시대로 `127.0.0.1` 만(`::1` 제외). IP 형식이 아니면 peer 로 되돌린다.
5. `cloudflared service install` 대신 다른 plist 와 같은 형식의 `com.rra.tunnel.plist` 를 쓴다(둘 중 하나만 — plist 주석·문서에 명시).
6. ADR 번호 0024(0023 다음). timeline·metrics 조각의 PR 번호는 `#TBD` — 통합 담당이 모을 때 채운다.

## 내가 할 일 (사람, 순서대로 — 어느 것도 아직 실행하지 않았다)
① **DNS 결정**: (a) Cloudflare — Cloudflare 대시보드에 `ai-edu-lab.co.kr` 존 추가 → 기존 레코드(특히 `agent` A 34.64.53.121) 전부 옮긴 뒤
   Gabia 에서 네임서버를 Cloudflare 가 준 2개로 변경, `dig +short NS ai-edu-lab.co.kr` 가 `*.ns.cloudflare.com` 이 될 때까지 대기.
   (b) 옮기지 않으면 Tailscale 대체(`docs/deploy-exposure.md` §5.5: `brew install --cask tailscale`, `tailscale serve --bg --https=443
   http://127.0.0.1:8000`, 동료 초대·ACL 443 만) — 아래 ②~⑥ 대신 §5.5 만 하면 된다.
② `brew install cloudflared && cloudflared tunnel login`(브라우저에서 존 `ai-edu-lab.co.kr` 선택 → `~/.cloudflared/cert.pem`).
③ `cloudflared tunnel create rra && cloudflared tunnel list` → ID 를 `deploy/cloudflared/config.example.yml` 의 `<TUNNEL_ID>` 에 넣어
   `~/.cloudflared/config.yml`(600) 로 저장 → `cloudflared tunnel route dns rra rra.ai-edu-lab.co.kr`.
   이미 터널이 있으면: 그 config.yml 의 404 규칙 앞에 ingress 한 묶음 추가 + `route dns <그 터널> rra.ai-edu-lab.co.kr` + 서비스 재시작, ④ 생략.
⑤(③ 다음, 기동 전) **Access 설정**: Zero Trust → Access controls → Applications → Create new application → Self-hosted and private →
   Add public hostname: Domain `rra.ai-edu-lab.co.kr`, Session duration `1 week`, 정책 Allow + Include Emails 3개, 로그인 방법 One-time PIN 만.
④ `cp deploy/launchd/com.rra.tunnel.plist ~/Library/LaunchAgents/ && launchctl load -w ~/Library/LaunchAgents/com.rra.tunnel.plist`
   (Mac mini 경로가 다르면 plist 의 `/Users/chan`·`/opt/homebrew` 를 먼저 맞춘다. 처음은 `cloudflared tunnel --config ~/.cloudflared/config.yml
   run rra` 로 손으로 1회 올려 ⑥ 을 보고 Ctrl-C 해도 된다).
⑥ `curl -sI https://rra.ai-edu-lab.co.kr | head -5` → `302` + `location: https://….cloudflareaccess.com/…` 이어야 한다. `200`/앱 헤더가
   보이면 **즉시** `launchctl unload -w ~/Library/LaunchAgents/com.rra.tunnel.plist`(또는 ingress 묶음 제거 후 재시작) 하고 이 파일에
   "Access 미설정" 을 적은 뒤 ⑤ 를 다시 한다. 통과하면 `config/api.yaml trust_cf_connecting_ip: true` 로 바꾸고 `launchctl kickstart -k
   gui/$(id -u)/com.rra.api`, 브라우저에서 Access 이메일 코드 → 앱 로그인(토큰) 확인.
- 내내 `rra api`(127.0.0.1:8000)·mlx(127.0.0.1:8080) 바인딩은 그대로. 공유기·방화벽에 포트를 열지 않는다. `tailscale funnel` 금지.

## 미완 항목
- 터널 생성·기동, Access 설정·확인(위 ①~⑥, 사람). `trust_cf_connecting_ip` 는 터널 기동 뒤 true 로.
- Mac mini 에서 `com.rra.tunnel.plist` 경로(`/opt/homebrew/bin/cloudflared`, `/Users/chan`) 확인.
- 시범 뒤 데이터 경계 재검토(internal 응답이 Cloudflare 엣지를 지남, ADR 0024).
