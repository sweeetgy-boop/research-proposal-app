## Argon(Gemini) 키 무효를 보이게 (fix/gemini-auth-visible, 2026-11-04, ADR 0055)

- 계기: 2026-10-30 09:32 마지막 성공 → 11-03 16:14:49 첫 실패 관찰 → 17:28 키 교체. Google 은 무효 키에 HTTP 400 `INVALID_ARGUMENT`/
  `API_KEY_INVALID` 로 답했다. 어댑터는 401/403 만 인증 실패로 보아서 일반 `LLMError` 가 됐고, 화면은 로컬 7B 로 조용히 대체됐다.
- 백엔드: `adapters/llm/openai_compat.py`(분류·경고 1줄·상태 기록), `_payload.error_codes`(열거값만), `errors.py`(`code`·`http_status`·
  `api_status`/`api_reason`, `LLMQuotaExceeded`), 포트 `application/ports/llm_status.py`, 규칙 `domain/rules/llm_status.py`, 어댑터
  `adapters/llm/status_file.py`(`<data_dir>/cache/llm_status.json`, `_DATA_LOCATIONS["llm_status"]`), 가짜 `adapters/fake/llm_status.py`
  (`RRA_FAKE_GEMINI_STATUS`), `daily_budget` 응답 시간 행 `error_code`, 조립 `build_llm_status`·`build_llm_health`, `/healthz` `llm`, `rra llm-check` 분류 출력.
- 웹: `components/frame/ArgonStatusBanner.tsx`(Layout 위쪽 막대 아래), `api/hooks.useArgonStatus`(60초·창 복귀), `auth/session.getSessionRole`·
  `useIsAdmin`, `lib/labels.ts` `ARGON_DOWN_TITLE`·`ARGON_REASON_LABELS`, `api/types.ts` `HealthOut.llm`.
- 프론트엔드 영향(API): `GET /healthz` 에 `llm: {gemini: "ok"|"key_invalid"|"quota"|"unavailable"|"unknown", since: string|null}` 추가.
  `status`·`version` 그대로. 응답 모델은 `dict` 라 `docs/openapi.json` 은 설명 문구만 바뀐다(통합 때 `rra api schema`).
- 시험: pytest 2424 → 2461, vitest 223 → 233, e2e 45 → 46 통과(+3 skip). lint-imports 8.
- 배포 뒤 확인: `curl -s http://127.0.0.1:8000/healthz` 에 `llm` 이 있는지. 처음에는 `unknown` 이고, 첫 Argon 호출 뒤 `ok` 다.
  필요하면 `rra llm-check --provider gemini --stage review` 1회(예산 1).
- 남은 일: 그림 생성(`image_gen.py`)은 이번 분류 밖이다. `recommend_projects._ask` 의 무로그 삼킴은 그 파일 작업이 끝난 뒤 고친다.
