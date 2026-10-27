# feat/login 진행 메모 (레인 A)

- 시작: 2026-10-27. 설계 읽기 완료(CLAUDE·CONTRIBUTING·architecture §4.5·§4.6·§9.2, security 어댑터, api/app.py, run_manager, web 로그인·레이아웃·e2e).
- 결정: run 소유자 = 가명 ID 의 저장소 키(`staff-<hmac12>`/`guest-<id>`, 디렉터리 단위 격리). 관리자(토큰)는 `local` + 전 사용자 조회.
