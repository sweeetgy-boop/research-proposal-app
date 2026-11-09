## 운영 점검 — 터널·로컬 모델 상태를 `/healthz` 에, `rra llm-check` 멈춤 금지 (feat/wave-c-ops-health, 2026-11-09, 레인 C, ADR 0062)

- 계기: 2026-11-03 `rra llm-check`(로컬) 멈춤 — 서버는 살아 있었고(종료 기록 없음) 프롬프트 8,887 토큰 요청 1건이 17:11:48 ~ 17:28:34
  서버를 붙들고 있었다. 그 사이 `GET /v1/models` 도 답이 없었고 클라이언트는 읽기 600초 × 재시도 3회를 기다렸다.
  Funnel 끊김은 배포 때만 확인하고 있었다.
- 백엔드: 규칙 `domain/rules/ops_status.py`, 포트 `application/ports/ops_status.py`(`OpsStatusPort`·`OpsStatusWriterPort`·
  `TunnelProbePort`·`LocalLlmProbePort`), 유스케이스 `usecases/ops_check.py`·`usecases/llm_check.py`, 어댑터
  `adapters/deploy/ops_status.py`(파일 600)·`adapters/deploy/tunnel_status.py`(normalize 순수 함수, 원문 버림)·
  `adapters/llm/local_status.py`, `openai_compat.first_request_timeout`(로컬 첫 전송만), `config_loader`(`api.yaml ops.tailscale_bin`,
  `llm.yaml timeout.first_request` 300, `_DATA_LOCATIONS["ops_status"]`), 조립 `build_ops_status`·`build_tunnel_probe`·
  `build_local_llm_probe`·`build_ops_check`·`build_llm_check_client`·`build_llm_check`, healthz 보기 `entrypoints/api/health_view.py`,
  CLI `entrypoints/cli_ops.py`(`rra ops check [--json]`).
- 운영 파일: `deploy/launchd/com.rra.opscheck.plist`(StartInterval 300), `com.rra.mlx.plist` ThrottleInterval 10 → 30 + 점검 메모,
  `tools/deploy.sh` 표에 `healthz tunnel`·`healthz llm.local` 두 줄(막지 않음), `deploy/README.md` §2 운영 점검 절.
- 웹: `components/frame/ArgonStatusBanner.tsx`(관리자에게만 "외부 접속 경로(Funnel) 내려감"·"로컬 모델 응답 없음"), `api/hooks.useOpsStatus`,
  `lib/labels.ts OPS_TUNNEL_DOWN·OPS_LOCAL_LLM_DOWN·opsAlertLines`.
- 프론트엔드 영향(API): `GET /healthz` 에 `tunnel`·`llm.local` 추가(계약대로, 모두 선택) — **app.py 연결은 통합 때**(아래).
- 통합 때 메인이 반영할 조립 변경(공용 파일): `app.py` healthz 에 `with_ops(out, ops_status)` + `create_app(ops_status=)`,
  `build_api(..., ops_status=build_ops_status(settings))`, `ports/__init__.py` export 4줄, `cli.py` `register_ops(sub)` 두 줄 +
  `cmd_llm_check` 를 `build_llm_check` 로(`--timeout` 인자). 정확한 조각은 PR 설명.
- 실측(2026-11-09 14:24, 운영 맥): `rra ops check` → `tunnel=ok llm_local=ok`.
- 사람 할 일: `com.rra.opscheck.plist` 설치, `com.rra.mlx.plist` 교체(재적재 시점), Tailscale 끄고 켜서 `tunnel` 값 변화 확인,
  `rra llm-check --timeout 5` 로 무응답 경로 1회 확인(서버가 바쁠 때).
- 시험: pytest 2,665 → 2,725(+60, skip 21 그대로), lint-imports 8, vitest 띠 10 → 16(전체 270 통과), typecheck 통과.
