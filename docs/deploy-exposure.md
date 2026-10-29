# 외부 공개 방식 비교 — Tailscale vs Cloudflare Tunnel (2026-10-26 비교, 2026-10-27 시범 결정 §5)

> **현재 운영(2026-10-29 문서 최신화)**: 2026-10-28 시범부터 실제 공개는 **Tailscale Funnel** `https://rra.taile5afcf.ts.net` → 127.0.0.1:8000
> + 앱 로그인(직원 사번·공용 계정·관리 토큰)이다(ADR 0047). 동료는 브라우저만 쓰고 Tailscale 앱 설치·초대는 필요 없다. 아래 §1~§5 의
> Cloudflare Tunnel + Access(ADR 0024, `rra.ai-edu-lab.co.kr`)는 DNS(Gabia) 때문에 띄우지 못한 **이전 계획**이고, "`tailscale funnel` 은
> 쓰지 않는다"는 문장들도 2026-10-27 당시 계획이다. 장애 대처·확인 방법은 `docs/pilot-guide.md` §1·§1.5.

앱은 127.0.0.1 에만 바인딩한다(보안 G·H). 동료 PC 에서 쓰려면 HTTPS 를 종단하고 접근을 제어하는 역프록시가 앞에
서야 한다. 둘 다 포트를 열지 않고(아웃바운드만), 앱의 자체 토큰(`RRA_API_TOKEN`)은 그대로 요구한다(이중 인증).
구현은 없다 — 아래는 결정에 필요한 비교와 설정 목록이다.

## 1. 비교

| 항목 | Tailscale (`tailscale serve`) | Cloudflare Tunnel (`cloudflared`) |
|---|---|---|
| 접근 범위 | 테일넷(초대한 계정·기기)만. 인터넷에 노출되지 않음 | 공개 URL. Cloudflare Access(이메일 OTP·SSO)로 제한 |
| 접근 제어 | 테일넷 ACL + 기기 단위. 동료는 Tailscale 앱 설치·로그인 필요 | Access 정책(허용 이메일·도메인). 동료는 브라우저만 |
| TLS | Tailscale 이 `*.ts.net` 인증서 자동 발급 | Cloudflare 엣지 종단. 터널 안은 암호화 |
| 도메인 | `<호스트>.<테일넷>.ts.net` (MagicDNS) | 보유 도메인 필요 (Cloudflare DNS) |
| 비용 | 개인 무료(사용자·기기 상한 넉넉) | 무료 플랜 가능 (Access 50명까지 무료) |
| 운영 부담 | 데몬 1개, 설정 명령 1줄 | cloudflared 데몬 + 대시보드 Access 설정 + 도메인 |
| 보안 I(로그) | 접속 로그는 Tailscale 관리 콘솔 | Access 로그는 Cloudflare 대시보드 |
| 데이터 경계 | 트래픽이 테일넷 안(WireGuard)에서만 | 평문은 아니지만 Cloudflare 엣지를 거친다 — 사내 자료(internal) 응답이 제3자 인프라를 지난다 |
| 적합한 경우 | **소수 동료 시연·시범 운영** (권장) | 불특정 다수·외부 기관 시연, Tailscale 설치가 불가한 환경 |

권장: 시범 운영은 Tailscale. 사내 자료(visibility=internal)가 응답에 섞이므로 제3자 엣지를 거치지 않는 쪽이 보안 설계
(§7 데이터 경계)와 맞는다. Cloudflare 는 동료가 앱 설치 없이 접속해야 할 때만.

## 2. 필요한 설정 (구현 없음 — 결정 뒤 그대로 실행)

### Tailscale
```bash
brew install --cask tailscale && open -a Tailscale          # Mac mini 에서 로그인 (조직 계정 권장)
tailscale serve --bg --https=443 http://127.0.0.1:8000     # REST 를 테일넷에 HTTPS 로
tailscale serve status                                      # https://<mac-mini>.<테일넷>.ts.net
# 동료: Tailscale 설치 → 같은 테일넷 초대 → 브라우저에서 위 주소 + X-RRA-Token (프론트엔드가 세션 쿠키로 처리)
# ACL(관리 콘솔): 동료 그룹 → Mac mini:443 만 허용. Streamlit(8501)은 공개하지 않는다.
```
`RRA_API_HOST` 는 127.0.0.1 그대로. `tailscale funnel` (인터넷 공개)은 쓰지 않는다. *(2026-10-26 계획 — 실제 시범은 Funnel 을 쓴다, ADR 0047)*

### Cloudflare Tunnel
```bash
brew install cloudflared && cloudflared tunnel login
cloudflared tunnel create rra && cloudflared tunnel route dns rra rra.<도메인>
# ~/.cloudflared/config.yml: ingress → service: http://127.0.0.1:8000 (나머지 http_status:404)
cloudflared service install                                 # launchd 로 상시
# Zero Trust 대시보드: Access 애플리케이션(rra.<도메인>) → 정책: 허용 이메일 목록, 세션 24h
```
앱 쪽 설정은 `config/api.yaml`(§5.2). Access 를 켜지 않으면 공개 URL 이 되므로 켜기 전에는 터널을 올리지 않는다.

## 3. 공통 점검
- `curl -I https://<주소>/healthz` → 200, `Content-Security-Policy` 등 앱 헤더가 그대로 나오는지.
- `/v1/precheck` 토큰 없이 401 — 역프록시가 토큰을 덧붙이지 않는지.
- 역프록시 뒤에서는 `X-Forwarded-*` 를 신뢰하지 않는다. 접속자 IP 는 `adapters/security/client_ip.client_ip` 가 정한다 —
  `config/api.yaml trust_cf_connecting_ip: true` 이고 peer 가 127.0.0.1(같은 호스트의 cloudflared)일 때만 `CF-Connecting-IP`.
- 공개 뒤 `rra runs purge`·백업이 계속 도는지 로그 확인.

## 4. 결정 항목 (사용자)
1. 시범 운영 대상이 소수 동료(Tailscale)인지, 외부 기관 시연(Cloudflare)인지.
2. Tailscale 이면 조직 테일넷 사용 여부(개인 계정 테일넷에 동료 초대 vs 조직 계정).
3. Cloudflare 이면 도메인·Access 이메일 목록.

## 5. 시범 결정 (2026-10-27, ADR 0024): Cloudflare Tunnel + Cloudflare Access, 앱 로그인 이중 인증

**결정** 시범 공개 주소는 `https://rra.ai-edu-lab.co.kr`. 동료는 브라우저만으로 접속한다 — Cloudflare Access(이메일 일회용 코드,
허용 이메일 3개, 세션 1주일) 를 지나 앱 로그인(`RRA_API_TOKEN` → 세션 쿠키) 을 한 번 더 한다(이중 인증).
**이유** (1) 동료 PC 에 아무것도 설치하지 않는다(Tailscale 은 앱 설치·테일넷 초대 필요). (2) 공개 주소이므로 Access 가 없으면 곧바로
인터넷 공개가 된다 — Access 가 켜진 것을 확인하기 전에는 터널을 올리지 않는다(규칙 4). (3) 앱·mlx 는 127.0.0.1 바인딩 그대로, 포트를
열지 않는다. 사내 자료(internal) 응답이 Cloudflare 엣지를 지나는 점은 §1 데이터 경계대로 알고 받아들인다(시범 한정, 운영 전 재검토).

### 5.1 현재 막힌 점 (2026-10-27 17:30 확인)
- **DNS 가 Cloudflare 가 아니다**: `dig +short NS ai-edu-lab.co.kr` → Gabia 네임서버 3개. `cloudflared tunnel route dns` 는 Cloudflare 가
  그 존을 관리할 때만 CNAME 을 만든다. → (a) 네임서버를 Cloudflare 로 옮기거나(기존 레코드 전부 Cloudflare 존에 먼저 옮긴 뒤 Gabia 에서
  NS 변경, 전파 수 시간) (b) 부분 위임(CNAME setup, Business 플랜) — 무료 플랜은 (a) 만. **`agent.ai-edu-lab.co.kr`(34.64.53.121, 다른
  호스트) 레코드는 그대로 옮겨 가야 하며 어떤 설정도 바꾸지 않는다.**
- **이 맥에 cloudflared·`~/.cloudflared`(cert.pem·config.yml) 가 없다.** 설치·로그인은 사람이 한다(§5.3).
- Access 는 터널을 올리지 않았으므로 **미확인**(§5.4).

### 5.2 앱 쪽 (이 PR 에서 끝남)
- `config/api.yaml`: `public_origin: https://rra.ai-edu-lab.co.kr`, `trust_cf_connecting_ip: false`(터널 기동 뒤 true). 둘 다 비밀 아님,
  `.env` 변경 없음. `config_loader.api_config` 가 읽고 `composition.api_middlewares`·`build_api` 가 넘긴다(파일 없으면 ""/false).
- `public_origin` 이 있으면: 그 Host 로 들어온 로그인의 세션 쿠키에 `Secure`(터널 안은 http 라 스킴만으로는 못 정한다. 127.0.0.1 직접
  접속은 그대로 — 로컬 e2e·Safari 호환), 쿠키 인증 상태 변경 요청·로그인의 `Origin` 검사에서 이 출처 허용(그 밖은 같은 Host 의
  http/https 만, `null`·타 출처 403). Origin 헤더가 없는 요청(curl 등)은 CSRF 토큰 규칙만 적용.
- `adapters/security/client_ip.py`: `client_ip(request, trust_cf)`·`access_user_hash(request)`. 거부 로그(`rra.api.auth`) 에는 접속자 IP 와
  `Cf-Access-Authenticated-User-Email` 의 sha256 앞 12자만 — 이메일 원문은 어디에도 남기지 않는다.
- `deploy/cloudflared/config.example.yml`(ingress: rra.ai-edu-lab.co.kr → http://127.0.0.1:8000, 나머지 404, 터널 ID 자리표시자),
  `deploy/launchd/com.rra.tunnel.plist`(`cloudflared tunnel --config ~/.cloudflared/config.yml --no-autoupdate run rra`, 비밀 없음).

### 5.3 터널 만들기 (사람, 이 맥에서 — 아직 실행하지 않았다)
```bash
brew install cloudflared                                   # 1) 설치 (/opt/homebrew/bin/cloudflared — plist 경로와 같다)
cloudflared tunnel login                                   # 2) 브라우저 로그인 → ~/.cloudflared/cert.pem (존 ai-edu-lab.co.kr 선택)
cloudflared tunnel create rra                              # 3) ~/.cloudflared/<TUNNEL_ID>.json (자격, 커밋 금지)
cloudflared tunnel list                                    #    ID 확인
sed "s#<TUNNEL_ID>#<실제 ID>#g" deploy/cloudflared/config.example.yml > ~/.cloudflared/config.yml && chmod 600 ~/.cloudflared/config.yml
cloudflared tunnel route dns rra rra.ai-edu-lab.co.kr      # 4) CNAME rra → <ID>.cfargotunnel.com (DNS 가 Cloudflare 일 때만 성공)
cloudflared tunnel --config ~/.cloudflared/config.yml run rra   # 5) 손으로 1회 — Access 확인(§5.4) 뒤 Ctrl-C
cp deploy/launchd/com.rra.tunnel.plist ~/Library/LaunchAgents/ && launchctl load -w ~/Library/LaunchAgents/com.rra.tunnel.plist   # 6) 상시
```
**이미 터널이 있을 때**(다른 서비스가 이 맥에서 같은 계정의 터널을 돌리고 있을 때): 새 터널을 만들지 말고 그 `config.yml` 의 ingress 에서
마지막 `http_status:404` 규칙 **앞**에 `- hostname: rra.ai-edu-lab.co.kr` / `service: http://127.0.0.1:8000` 한 묶음을 넣고,
`cloudflared tunnel route dns <그 터널> rra.ai-edu-lab.co.kr` 뒤 그 서비스를 재시작한다(`launchctl kickstart -k gui/$(id -u)/<라벨>`
또는 unload/load). `com.rra.tunnel.plist` 는 등록하지 않는다(중복 기동 금지). `cloudflared service install` 을 쓴 경우 라벨은
`com.cloudflare.cloudflared`.

### 5.4 Access 확인 (터널 기동 직후, 반드시)
```bash
curl -sI https://rra.ai-edu-lab.co.kr | head -5
```
- `HTTP/2 302` + `location: https://<팀>.cloudflareaccess.com/...` → Access 가 앞에 있다. 정상.
- `HTTP/2 200`(앱 응답, `content-security-policy` 헤더가 보임) 또는 `/healthz` 가 `{"status":"ok"}` → **Access 미설정 = 인터넷 공개 상태.**
  즉시 `~/.cloudflared/config.yml` 에서 그 hostname ingress 묶음을 빼고 재시작(또는 `launchctl unload -w …com.rra.tunnel.plist`),
  `docs/status.d/feat-tunnel.md` 에 "Access 미설정" 기록 → §5.5 대체 경로.
- Access 설정(터널을 올리기 **전**에): Cloudflare 대시보드 → Zero Trust → Access controls → Applications → Create new application →
  Self-hosted and private → Add public hostname: Domain `rra.ai-edu-lab.co.kr`(경로 없음), Session duration `1 week`, Access policies →
  새 정책 Action Allow, Include → Emails 에 허용 이메일 3개(여기 적지 않는다), 로그인 방법은 Settings → Authentication → Login methods 에
  One-time PIN 만 두고 저장. 구 UI 는 Access → Applications → Add an application → Self-hosted(같은 항목).
- Access 통과 뒤 앱 로그인(토큰) 화면이 보여야 한다. `/v1/precheck` 는 토큰 없이 401(§3).

### 5.5 대체 경로 (DNS 를 옮기지 않기로 하면): Tailscale serve
동료마다 Tailscale 앱 설치·테일넷 초대가 필요하지만 도메인·DNS·Access 가 전혀 필요 없고 트래픽이 테일넷 밖으로 나가지 않는다(§1 권장안).
```bash
brew install --cask tailscale && open -a Tailscale        # 1) 이 맥에서 로그인 (조직 계정 권장)
tailscale serve --bg --https=443 http://127.0.0.1:8000   # 2) https://<이 맥 이름>.<테일넷>.ts.net → 127.0.0.1:8000 (Tailscale 이 인증서 발급)
tailscale serve status                                    # 3) 주소 확인. 끄기: tailscale serve --https=443 off (전부: tailscale serve reset)
```
동료: Tailscale 설치 → 초대 수락(관리 콘솔 Users → Invite) → 브라우저에서 위 `*.ts.net` 주소 → 앱 로그인(토큰). 관리 콘솔 Access controls
→ ACL: 동료 그룹은 이 맥의 443 만(`"dst": ["<이 맥>:443"]`), 8000·8080·8501 은 열지 않는다. `tailscale funnel`(인터넷 공개)은 쓰지
않는다 *(2026-10-27 계획 — 실제 시범은 Funnel, ADR 0047)*. 앱 쪽: `config/api.yaml public_origin` 을 `https://<이 맥 이름>.<테일넷>.ts.net` 으로 바꾸면 쿠키 Secure·Origin 허용이 그대로
적용된다(`trust_cf_connecting_ip` 는 false 유지 — Tailscale 은 CF 헤더를 붙이지 않는다). 명령의 정확한 형태는 설치한 버전의
`tailscale serve --help` 로 한 번 더 확인한다.
