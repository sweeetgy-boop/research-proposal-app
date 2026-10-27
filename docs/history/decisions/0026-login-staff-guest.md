# ADR 0026 — 로그인: 직원 사번(HMAC)·공용 계정(scrypt)·관리 토큰, run 소유자 가명 격리 (2026-10-27, 레인 A)

## 배경
시범 사용자는 철도연구원 직원(사번)과 그 외 사용자(공용 계정 1개)로 나뉜다. 저장소는 공개라 사번·비밀번호·해시를 커밋할 수 없고,
run·로그·manifest 에 사번 원문이 남으면 안 된다. 기존 `X-RRA-Token`(API·CLI·MCP·관리) 은 유지해야 한다. 비용(Gemini)·자료 범위(internal)도
사용자 종류별로 보호해야 한다.

## 선택지
1. 사번을 그대로 저장·표시 — 개인정보가 run·로그에 남는다. 제외.
2. 사번 HMAC-SHA256(서버 비밀 키) + 앞 12자 가명, 비밀번호 scrypt(무작위 salt) — 원문 없이 등록 여부만 판정. 비밀 키는 `data/auth/secret`(600).
3. 외부 IdP(Cloudflare Access 만) — 앱 안의 사용자 구분·소유권이 없다. 레인 W 의 Access 는 앞단 이중 인증으로만 둔다.

## 결정
- 2. `Principal(kind, id)` — `staff:<hmac12>` / `guest:<아이디>` / `admin:local`. run 저장소 키는 `staff-…`/`guest-…`/`local`(디렉터리 단위 격리,
  기존 `runs/local/` 은 관리자 것). 모든 run 경로가 소유자를 검사하고 남의 run 은 404(존재 여부 비노출). 관리자는 전부 본다.
- 실패 문구는 하나("사번 또는 아이디·비밀번호를 확인하세요"). 잠금: 계정 5회 연속 → 10분, IP 20회/10분, 전체 50회/10분 초과 → 응답 지연 2초.
  접속자 IP 는 레인 W 의 `client_ip`(CF-Connecting-IP 는 설정 + peer 127.0.0.1 일 때만).
- 공용 계정은 `visibility=internal` 제외(`auth.yaml guest.include_internal=false`): 저장소 래퍼 한 곳에서 걸러 검색·유사과제·근거·추천이 같이 따른다.
- 비용: 사용자별 일일 생성 상한(공용 10·직원 20)은 run 생성 시각으로 세고, Gemini 는 provider 단위 일일 호출 상한(300, 파일 카운터)으로 막는다.
  소진 시 검토를 건너뛰고(`draft_review_skipped=budget`) 화면에 알린다. 생성 동시성 1·대기 3 은 그대로.
- 등록은 CLI(`rra auth …`, getpass)로만. 웹은 두 탭 + "관리자" 링크 아래 토큰. 상단에는 종류 라벨만.

## 결과
- 새 모듈: `domain/models/principal.py`, `domain/rules/auth_policy.py`, `application/ports/auth.py`, `application/usecases/login.py`,
  `application/services/scoped_repository.py`, `adapters/auth/file_store.py`, `adapters/llm/daily_budget.py`, `adapters/fake/auth.py`,
  `config/auth.yaml`, 테스트 5파일(+26), e2e `login.spec.ts`.
- 비밀 키를 잃으면 가명이 바뀌어 기존 run 소유권이 끊긴다 — 백업 대상. 잠금 상태는 메모리.
