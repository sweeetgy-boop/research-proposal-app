# 계약 — `/healthz` 운영 상태 칸 `tunnel`·`llm.local` (2026-11-09, 레인 C)

`/healthz` 는 인증 없이 인터넷에서 보인다(ADR 0055). **값만** — 경로·IP·호스트명·계정·오류 문구·건수 금지.

## 1. 응답
```json
{
  "status": "ok",
  "version": {"commit": "…", "short": "…", "deployed_at": "…"},
  "llm": {"gemini": "ok|key_invalid|quota|unavailable|unknown", "since": "…",
          "local": "ok|unavailable|unknown"},
  "tunnel": "ok|down|unknown"
}
```
- `llm.local`: 로컬 모델 서버(mlx, 127.0.0.1) — `ok` 마지막 점검에서 응답, `unavailable` 응답 없음·연결 실패·launchd 미기동,
  `unknown` 점검 기록 없음. 점검은 5분 주기(아래 3)와 `rra llm-check --local` 결과 둘 다 같은 상태 파일에 쓴다.
- `tunnel`: Tailscale Funnel 공개 경로 — `ok` = `tailscale status` 가 BackendState Running **그리고** `tailscale funnel status` 에
  "(Funnel on)" 이 있음, `down` = 둘 중 하나라도 아님(Tailscale 꺼짐·Funnel 내려감), `unknown` = 점검 기록 없음·명령 없음(개발 맥).
  기록에는 정해진 열거값만 — 명령 출력 원문(IP·계정·DNS 이름)은 저장·로그하지 않는다.
- `version`·`llm.gemini`·`since` 는 종전 그대로. 새 칸은 모두 선택(없으면 웹은 unknown 으로 본다).

## 2. 웹 (`web/src/api/types.ts` `HealthOut` — 0단계에서 칸 추가)
```ts
llm?: { gemini: ArgonState; since: string | null; local?: LocalLlmState };
tunnel?: TunnelState;
```
관리자 띠(`components/frame/ArgonStatusBanner.tsx`, 레인 C): `tunnel === "down"` → "외부 접속 경로(Funnel) 내려감", `llm.local === "unavailable"` →
"로컬 모델 응답 없음". 둘 다 **관리자에게만**(직원·공용 계정 화면은 종전 Argon 띠만). 문구는 `web/src/lib/labels.ts`.

## 3. 상태 파일·점검 (레인 C)
- 상태 파일 `data/cache/ops_status.json` — `{"tunnel": {"state", "checked_at"}, "llm_local": {"state", "checked_at", "since"}}`, 권한 600, 열거값·시각만.
  읽기 포트 `application/ports/ops_status.py OpsStatusPort`(runtime_checkable) — `/healthz` 는 이 포트로만 읽는다(명령 실행 안 함, 응답 지연 없음).
- 점검 주기 5분: launchd `com.rra.opscheck.plist`(StartInterval 300) → `rra ops check`(새 CLI, 레인 C) 가 `tailscale status --json`·
  `tailscale funnel status`·로컬 모델 `GET /v1/models`(타임아웃 5초) 를 보고 상태 파일만 갱신. 출력은 열거값 한 줄.
  `tailscale` 명령 경로는 `config/api.yaml ops.tailscale_bin`(기본 `/Applications/Tailscale.app/Contents/MacOS/Tailscale`, 없으면 unknown).
- `rra llm-check`: `--timeout` 기본 120초(로컬)·600초(Argon, `llm.yaml timeout.read`) — 무응답이면 `unavailable` 기록 + 한 줄 안내 후 종료(멈춤 금지).
- mlx 재시작 정책: `com.rra.mlx.plist` `KeepAlive`·`ThrottleInterval` 확인, 첫 요청(모델 적재) 타임아웃은 `llm.yaml timeout.first_request`(새, 기본 300).

## 4. 배포 스크립트
`tools/deploy.sh` 5단계 확인에 `/healthz tunnel`·`llm.local` 값을 기록(`docs/history/deploys/<시각>.md` 표에 두 줄). 값이 down·unavailable 이어도
배포를 막지 않고 표시만.
