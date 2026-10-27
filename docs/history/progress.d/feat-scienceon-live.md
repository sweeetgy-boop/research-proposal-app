# 레인 B 진행 기록 — feat/scienceon-live (2026-10-27)

- 10:55 시작. worktree `.env` 복사(600). `rra sources check --source scienceon` → ValueError "인증키는 32바이트" (0.3 s).
- 11:00 원인: `.env` 의 `RRA_SCIENCEON_CLIENT_ID`(32자)·`RRA_SCIENCEON_KEY`(64자)가 서로 바뀜. 공식 가이드(API 인증 안내):
  client_id 64자, 인증키 32자. 키 변형(hex 해독·앞/뒤 32자) 3회 모두 XML E5001 → 접근 바꿈(가이드 확인).
- 11:06 worktree `.env` 만 두 값 교체(원본 미수정) → 토큰 발급 성공 (JSON, 0.1 s). 표준·urlsafe base64 둘 다 수락.
- 11:07 openapicall.do 406 → GuardedClient.get_bytes 가 Accept: application/json 만 보냄. accept_types 로 Accept 헤더 생성.
- 11:08 `sources check` ok: ARTI 1,858 · REPORT 370 (질의 "철도 궤도", 토큰+2건 2.2 s). fixture 3건 녹화
  (ARTI·REPORT·PATENT 각 10건, PATENT 총 911). 토큰·client_id 는 REDACTED.
- 11:15 normalize 재작성(확정 metaCode, 사람 이름 미저장, 기관 orgs), client per_query_limit·PATENT, 녹화 도구 이름 제거.
- 11:25 python -I 가 PYTHONPATH 를 무시해 조사 스크립트가 원본 코드(406)로 돌았음 → 재실행. 질의 19개 × 3 target 총건수 조사 58회
  57 s(1 req/s). 13개 질의 확정, sources.yaml 반영(PATENT·row_count 100·per_query_limit 80·예산 48).
- 11:35 fixture·단위 테스트 통과. status.d·timeline.d·ADR 0015 작성. 드라이런(임시 DB, limit 5) 시도.
- 11:45 드라이런 `RRA_DB_PATH=<임시> rra ingest --source scienceon --limit 5` → fetched 5·normalized 5·stored 5·chunks 5, 16 s
  (임베딩 모델 로드 포함, 요청 2회). 실 DB 는 손대지 않음.
- 11:55 전체 검사 통과: pytest 1,251 passed·17 skipped, lint-imports 8 kept, ruff clean. 커밋 준비.
