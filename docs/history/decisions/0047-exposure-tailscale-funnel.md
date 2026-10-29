# ADR 0047 — 외부 공개는 Tailscale Funnel(공개 주소 `*.ts.net`) + 앱 로그인 — Cloudflare 계획 대체 (2026-10-28, 사후 기록)

> 2026-10-29 문서 최신화(docs/final-docs)에서 정리한 사후 기록이다. 결정 자체는 2026-10-28 오전 시범 시작 때 운영에서 내려졌고,
> 근거는 아래 파일들에 흩어져 있었다.

## 배경
ADR 0024 는 시범 공개를 Cloudflare Tunnel + Access(`rra.ai-edu-lab.co.kr`)로 정했으나, 도메인 DNS 가 Gabia 에 있어 터널을 띄우지
못했다(`docs/status.d/feat-tunnel.md`, `docs/final-check-2026-10-27.md`). 2026-10-28 아침 3명 시범을 시작해야 했고, 동료 PC 에 앱 설치·
테일넷 초대를 요구하지 않는 경로가 필요했다. `docs/deploy-exposure.md` §1·§5.5 는 Tailscale `serve`(테일넷 안)만 다뤘고
`funnel`(인터넷 공개)은 쓰지 않는다고 적어 두었다.

## 결정
- 운영 맥의 Tailscale **Funnel** 로 `https://rra.taile5afcf.ts.net` → `127.0.0.1:8000` 을 공개한다. 동료는 브라우저만 있으면 된다.
- 접근 제어는 앱 로그인(직원 사번·공용 계정·관리 토큰, ADR 0026)이 맡는다. Cloudflare Access 같은 앞단 인증은 없다.
- `config/api.yaml public_origin` 을 이 주소로 바꿔 Secure 쿠키·Origin 검사가 이 주소 기준이 된다(2026-10-28 13:10).
- Funnel 뒤에서는 접속자가 모두 127.0.0.1 로 보이므로, 127.0.0.1 peer 일 때만 `X-Forwarded-For` 맨 오른쪽을 접속자 IP 로 쓰고 모르면
  IP 잠금을 걸지 않는다(#79, `api.yaml trust_forwarded_from_loopback`).
- 배포 스크립트는 Funnel 상태를 확인만 한다(`tools/deploy.sh` "Funnel on"). 켜고 끄기는 사람 작업.

## 결과
- 2026-10-28 11:29 첫 배포 기록부터 외부 주소 확인 ok(`docs/history/deploys/2026-10-28-1129.md`), 2026-10-29 09:30 배포 뒤
  인터넷 쪽 점검 3곳 200(`docs/history/deploys/2026-10-29-0930.md`).
- 2026-10-28 15:3x 외부 접속 장애: Funnel 중계가 이 맥으로 넘기지 않아 TLS 가 끊김 → 사람이 Funnel 을 다시 등록(`docs/final-check-2026-10-28.md`,
  `docs/pilot-guide.md` §1.5). 이 맥에서 하는 확인은 tailnet 경로라 소용없고 check-host.net·휴대폰 데이터망으로 확인한다.
- 남은 위험: 앞단 인증이 없어 로그인 화면이 인터넷에 열려 있다(계정·IP 잠금·전체 지연으로 막음). 운영 맥이 꺼지면 접속이 끊긴다.
  회사 도메인(`rra.ai-edu-lab.co.kr`) + Cloudflare 는 DNS 이전 뒤 다시 검토할 수 있다(ADR 0024 는 이전 계획으로 남김).
