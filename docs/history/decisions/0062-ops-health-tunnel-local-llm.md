# ADR 0062 — 운영 점검을 `/healthz` 에 열거값으로: 터널(Funnel)·로컬 모델, `rra llm-check` 멈춤 금지 (2026-11-09, feat/wave-c-ops-health)

## 맥락
- **2026-11-03 `rra llm-check`(로컬) 멈춤.** 운영 로그(`~/Library/Logs/rra-mlx.err.log`, 경로·IP 는 적지 않는다) 재구성:
  - 11-03 11:08 서버 기동(`Starting httpd`) → 16:13 ~ 17:11 요청 13건 정상 응답(각 10~60초).
  - 17:11:48 요청 1건 — 프롬프트 8,887 토큰. 프롬프트 처리는 17:11:55 에 끝났으나 **완료 기록(Prompt Cache 줄)이 17:28:34 에야 남았다**
    — 생성 1건이 약 16분 40초 동안 서버를 붙들고 있었다(긴 생성 또는 멈춘 생성; 어느 쪽인지는 로그로 가릴 수 없다).
  - 같은 17:28:34 에 `GET /v1/models`(llm-check 의 served_model 확인)가 처음 응답받았다 — 그 사이 다른 요청은 답을 받지 못했다.
  - 서버는 죽지 않았다: `launchctl print` 에 종료 기록 없음(`last exit code = (never exited)`), Traceback 도 10-28 BrokenPipe 1건뿐,
    OOM·포트 충돌 흔적 없음. 11-04 16:43·11-05 09:09 의 재기동은 손으로 한 것(재부팅 포함).
- 클라이언트 쪽: `llm.yaml timeout.read` 600초(ADR 0038 "10분 동안 한 바이트도 없음" 안전선) × `retries.attempts` 3 — 로컬 서버가 붙들려
  있으면 llm-check 는 최대 30분을 조용히 기다린다. `GET /v1/models` 도 같은 클라이언트라 같은 제한이다. 모델 적재 중의 첫 요청에 대한
  별도 제한은 없었다.
- 외부 접속 경로(Tailscale Funnel, ADR 0047)는 배포 때(`tools/deploy.sh`)만 확인했다. 2026-10-28 15:3x 처럼 Funnel 중계가 끊기면
  동료가 접속해 보기 전까지 모른다.
- ADR 0055 가 Argon 상태를 `/healthz llm.gemini` 열거값 + 관리자 띠로 드러낸 방식이 이미 있다. `/healthz` 는 인증 없이 인터넷에서 보인다.

## 선택지
1. API 프로세스가 `/healthz` 요청마다 tailscale 명령·로컬 서버를 직접 찌른다 — 공개 경로의 응답이 느려지고(명령 10초), 외부에서
   점검 빈도를 조절당한다.
2. API 가 백그라운드 스레드로 주기 점검 — 프로세스 안에 또 하나의 상시 작업, 재시작마다 상태 공백.
3. **launchd 5분 주기의 짧은 CLI(`rra ops check`)가 상태 파일에 열거값만 적고, `/healthz` 는 파일만 읽는다.** 점검 실패·명령 없음은
   unknown, 오래된 기록도 unknown.

## 결정
3 을 택한다 (계약 `docs/contracts/healthz-status.md` 그대로).
- **규칙** `domain/rules/ops_status.py`(순수 함수): tunnel = BackendState "Running" AND "(Funnel on)" → ok, 아니면 down, 값을
  못 얻으면 unknown; llm_local = GET /v1/models 2xx → ok, 아니면 unavailable; 마지막 점검이 15분(5분 주기 × 3)보다 오래되면 unknown.
- **포트** `application/ports/ops_status.py` — `OpsStatusPort`(읽기 전용 `snapshot()`, `/healthz` 용), `OpsStatusWriterPort`(`record`),
  `TunnelProbePort`(→ `TunnelProbe(backend_state, funnel_on)`), `LocalLlmProbePort`(→ bool|None). 모두 runtime_checkable, 동기.
- **유스케이스** `usecases/ops_check.OpsCheck` — 점검 1회 → 상태 파일, unknown 은 적지 않는다(이전 기록이 15분 뒤 저절로 unknown).
  `usecases/llm_check.LlmCheck` — 왕복 1회, 로컬이면 결과(ok / 무응답 unavailable)를 같은 파일에 적고 예외 대신 결과로 돌려준다.
- **어댑터** `adapters/deploy/ops_status.FileOpsStatus`(`data/cache/ops_status.json`, 600, `_DATA_LOCATIONS["ops_status"]`),
  `adapters/deploy/tunnel_status.TailscaleProbe`(subprocess 2회, 10초; `normalize_status_json`·`normalize_funnel_text` 순수 함수 —
  BackendState 값·표식 유무만 남기고 **출력 원문(IP·호스트명·계정)은 버린다**, 로그에도 없음), `adapters/llm/local_status.LocalLlmProbe`
  (GET /v1/models 5초, 루프백만). `OpenAICompatLLM.first_request_timeout` — 로컬 provider 의 **첫 전송**만 read 를
  `llm.yaml timeout.first_request`(기본 300) 이상으로.
- **조립** `build_ops_status`·`build_tunnel_probe`(명령 파일 없으면 None)·`build_local_llm_probe`·`build_ops_check`·
  `build_llm_check_client`(읽기 제한 인자·재시도 1회)·`build_llm_check`. `/healthz` 연결은 `entrypoints/api/health_view.with_ops`
  (app.py 는 공용 파일 — 통합 때 두 줄).
- **진입점** `entrypoints/cli_ops.register` → `rra ops check [--json]`(출력 `tunnel=ok llm_local=ok` 한 줄). `rra llm-check --timeout`
  (기본 로컬 120초·Argon 은 timeout.read, 재시도 없음; 무응답이면 `unavailable` 기록 + 한 줄 안내 후 종료) — cli.py 연결은 통합 때.
- **launchd** `deploy/launchd/com.rra.opscheck.plist`(StartInterval 300, RunAtLoad, 원 저장소 venv·`RRA_DATA_DIR`), `com.rra.mlx.plist`
  ThrottleInterval 10 → 30(KeepAlive SuccessfulExit=false 유지). 설치는 사람(deploy/README.md §2).
- **화면** 관리자 띠(`ArgonStatusBanner`)에 `tunnel === "down"` → "외부 접속 경로(Funnel) 내려감", `llm.local === "unavailable"` →
  "로컬 모델 응답 없음". 직원·공용 계정은 종전 Argon 띠만. 문구 `lib/labels.ts opsAlertLines`, 훅 `useOpsStatus`(같은 /healthz 캐시).
- **배포 스크립트** 5단계 확인에 `/healthz tunnel`·`llm.local` 두 줄 기록 — 값이 나빠도 막지 않는다.

## 이유
- 공개 경로는 파일만 읽으므로 응답 지연·명령 실행이 없고, 외부에서 알 수 있는 것은 "지금 되는가" 열거값뿐이다(ADR 0055 와 같은 원칙).
- 점검을 launchd 에 두면 API 가 죽어도 점검은 계속되고, 점검이 죽으면 15분 뒤 unknown 으로 드러난다(둘 다 "ok 처럼 보임"을 막는다).
- llm-check 는 진단 도구다 — 서버가 붙들려 있을 때 30분을 기다리는 대신 2분 안에 "응답 없음"을 말하는 편이 맞다. 생성 경로의 600초
  안전선(ADR 0038)은 바꾸지 않는다.

## 결과
- 2026-11-09 14:24 운영 맥에서 `rra ops check` 1회: `tunnel=ok llm_local=ok`(상태 파일 600 생성). Tailscale 을 끄고 켜서 값이
  바뀌는지는 사람이 확인한다(운영 변경은 레인이 하지 않는다).
- pytest 2,665 → 2,7xx(통합 뒤 확정), lint-imports 8 유지, vitest 띠 10 → 16.
- 남은 일(통합 때 메인): app.py healthz 두 줄·`build_api(ops_status=)`, cli.py `register_ops(sub)`·`cmd_llm_check` 의 `--timeout`,
  `ports/__init__.py` export, plist 설치(`com.rra.opscheck` 등록·`com.rra.mlx` 교체 — 교체는 모델 재적재 시점에).
- 밝히지 못한 것: 17:11:48 요청이 "느린 생성"이었는지 "멈춘 생성"이었는지. mlx_lm.server 는 요청 로그에 응답 길이를 남기지 않는다.
  다시 생기면 `rra ops check` 의 `llm_local=unavailable`(5초 무응답)이 먼저 알린다.
