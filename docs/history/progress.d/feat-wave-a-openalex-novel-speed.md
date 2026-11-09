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
- (1) 커밋 9ff63fe: `domain/rules/source_limits.py`(SourceRateLimited·안내), LiveOpenAlex 429 대기 상한 5초 → 즉시 건너뜀,
  live_search `error`+notice(`live.rate_limited`), GuardedClient h11 LocalProtocolError 재시도, sources.yaml openalex.max_backoff_sec 60,
  fixture works_pigeon.json(12건, 이름 제거)·rate_limited_429.json, 테스트 +17.
- (2) 커밋 423b200: recommend_projects novel 경로 gather(novelty ∥ analogies ∥ references), progress 콜백, timings,
  novelty 는 새 문서(new>0) 있을 때만 규칙 판정 재실행, progress_routes.register_recommend_stream(SSE),
  recommend_metrics 3칸, feedback_stats 갈래·단계 중앙값, views 분리. 전체 pytest 2698 passed / 21 skipped, lint-imports 8 kept.
- 측정 시작(14:50~): 전 = 운영 API(2c7497f, 127.0.0.1:8000, HTTP), 후 = worktree build_api 프로세스 안(ASGI, 메모리 sink).
  변형 6개(비둘기 아이디어 표현만 다르게, 각 arm 3개씩 모두 콜드) 교대로.
- 측정 1: 전 v0(운영 API) 과제안 229.9초(측정 줄 213.6, load 7.9 — 레인 D pytest·평가 동시) · 후 v1(heavy lock 990초 대기 뒤, load 2.8)
  69.7초(유스케이스 60.2 = search 19.0 ∥ analogy 13.5 → generate 28.5). 후 v1 OpenAlex 실시간: 넓힌 검색 40건·유추 검색 30건(ok),
  ScienceON 유추 세션은 ScienceOnError(3 target), NTIS ip_blocked. 두 arm 모두 ② 규칙 단계 때 주 실시간 세션은 pending(15초 넘김,
  키워드 Argon·로컬 6초 timeout → 규칙 키워드).
- 측정 2~4: 전 v2 61.7초(ScienceON 즉시 error 라 넓힌 검색이 빨리 끝남, OpenAlex ok 30) · 후 v3 81.3초(유스케이스 67.8 = search 21.9 ∥
  analogy 13.3 → generate 31.8; rule_stage 85.5초는 모델 로드 포함) · 전 v4 72.8초(OpenAlex ok 30, ScienceON error). 후 v3 OpenAlex: 넓힌 40·유추 30.
  recommendations 호출 안에는 `current()` 의 AI 판정 합류(~10초)가 들어간다(두 arm 같음).
- 측정 5: 후 v5 65.2초(유스케이스 54.8 = search 14.9 ∥ analogy 8.8 → generate 26.3) — OpenAlex 익명 429 가 실제로 와서 새 코드가
  `live.rate_limited` 로 즉시 건너뜀(coverage openalex error). 요약: 전 유스케이스 p50 62.5/p90 183.3, 후 p50 60.2/p90 66.3 (status.d 표).
- 문서 조각(status.d·timeline.d·ADR 0060)·PR 설명 작성 → 커밋·푸시·PR.
