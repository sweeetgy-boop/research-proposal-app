# feat/wave-a-openalex-novel-speed 진행 메모 (레인 A, 2026-11-09)

- 시작. main 434581b 기준 worktree. 계약 `docs/contracts/wave-1109.md`·`novel-recommend.md`·ADR 0057 읽음.
- (1) OpenAlex 오류 원인: 운영 `rra-api.err.log` 에 `live.source_failed source=openalex err=RateLimited` 와
  `err=LocalProtocolError` 두 줄(11-05 16:29). 야간 적재 로그에도 `[openalex] 실패: RateLimited`.
  실호출 3회 확인: 익명 search 요청에 HTTP 429 `Retry-After: 30` — "Anonymous search is temporarily rate-limited
  while the search cluster is under elevated load … use a free API key"(2회), 3회째는 200 + "No API key, so this
  request shares one free daily budget with everyone on your network's IP"(x-ratelimit-limit 1000).
  → 원인 = OpenAlex 정책 변경(익명 검색 제한·IP 공유 일일 예산). `.env` 에 `RRA_OPENALEX_API_KEY`·`RRA_OPENALEX_MAILTO` 없음.
  `LocalProtocolError` 는 httpcore 가 `h11.LocalProtocolError` 를 감싸지 않는 경로(`_send_event`)라 `httpx.TransportError`
  로 잡히지 않고 그대로 올라온 것(재시도·연결 폐기 없이 실패).
- 운영 수치: Retry-After 30 ≤ max_backoff 30 이라 30초 자면서 per_source_timeout(10/15초)에 걸려 timeout, 31 이면 즉시 RateLimited.
- 고칠 방향: 실시간 OpenAlex 는 429 Retry-After 를 짧게 끊어(fail-fast) `error` + 안내("익명 검색 제한 — API 키 필요"),
  GuardedClient 는 h11 LocalProtocolError 를 전송 오류처럼 재시도, fixture(429 본문·비둘기 질의 200 응답, 이름 제거) 추가.
- (2) 속도: novelty(넓힌 검색 + 새 자료 있을 때만 규칙 판정) ∥ analogies 를 gather, 단계 시간 3칸, SSE 는 `progress_routes.py` 안에서만
  (app.py·ports/__init__.py 는 건드리지 않음 — 연결 줄은 PR 설명으로).
