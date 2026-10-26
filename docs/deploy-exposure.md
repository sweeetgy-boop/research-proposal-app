# 외부 공개 방식 비교 — Tailscale vs Cloudflare Tunnel (2026-10-26, 결정 전)

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
`RRA_API_HOST` 는 127.0.0.1 그대로. `tailscale funnel` (인터넷 공개)은 쓰지 않는다.

### Cloudflare Tunnel
```bash
brew install cloudflared && cloudflared tunnel login
cloudflared tunnel create rra && cloudflared tunnel route dns rra rra.<도메인>
# ~/.cloudflared/config.yml: ingress → service: http://127.0.0.1:8000 (나머지 http_status:404)
cloudflared service install                                 # launchd 로 상시
# Zero Trust 대시보드: Access 애플리케이션(rra.<도메인>) → 정책: 허용 이메일 목록, 세션 24h
```
앱 쪽 추가 설정 없음. Access 를 켜지 않으면 공개 URL 이 되므로 켜기 전에는 터널을 올리지 않는다.

## 3. 공통 점검
- `curl -I https://<주소>/healthz` → 200, `Content-Security-Policy` 등 앱 헤더가 그대로 나오는지.
- `/v1/precheck` 토큰 없이 401 — 역프록시가 토큰을 덧붙이지 않는지.
- 역프록시 뒤에서는 `X-Forwarded-*` 를 신뢰하지 않는다(앱은 클라이언트 IP 를 쓰지 않는다).
- 공개 뒤 `rra runs purge`·백업이 계속 도는지 로그 확인.

## 4. 결정 항목 (사용자)
1. 시범 운영 대상이 소수 동료(Tailscale)인지, 외부 기관 시연(Cloudflare)인지.
2. Tailscale 이면 조직 테일넷 사용 여부(개인 계정 테일넷에 동료 초대 vs 조직 계정).
3. Cloudflare 이면 도메인·Access 이메일 목록.
