# feat/wave-c-ops-health 진행 메모 (레인 C — mlx 멈춤·터널 감시)

- 2026-11-09 14:10 시작. main 434581b 기준 worktree. 계약 `docs/contracts/healthz-status.md`·wave-1109·ADR 0055·0047 읽음.
  기준 pytest 2,665 passed / 21 skipped.
- 14:15 mlx 원인 조사(읽기만): `launchctl print` state running·종료 기록 없음(pid 는 11-05 09:09 재부팅 때 것). `rra-mlx.err.log`:
  11-03 17:11:48 요청(프롬프트 8,887 토큰)이 17:28:34 까지 서버를 붙듦 → 그 사이 `GET /v1/models` 무응답. OOM·포트 충돌·Traceback 없음
  (10-28 BrokenPipe 1건뿐). 클라이언트는 read 600 × attempts 3. 지금 서버는 `/v1/models` 200 (모델 3종 목록).
- 14:20 구현: domain/rules/ops_status → ports/ops_status → usecases/ops_check·llm_check → adapters(deploy/ops_status·tunnel_status,
  llm/local_status) → config_loader(ops·first_request·데이터 위치) → composition build_* 6개 → cli_ops·health_view.
  코디네이터 지시로 공용 파일(app.py·ports/__init__·cli.py·build_api 본문) 수정은 되돌리고 PR 설명으로 옮김.
- 14:24 `rra ops check` 실측(운영 맥): `tunnel=ok llm_local=ok`, `data/cache/ops_status.json` 600.
- 14:28 웹: labels·useOpsStatus·ArgonStatusBanner 관리자 두 줄, vitest 16 통과(+6), typecheck 통과.
- 14:35 plist(opscheck 새 파일, mlx ThrottleInterval 30)·deploy.sh 두 줄·README §2 절·tests/deploy·ADR 0062·조각 문서.
