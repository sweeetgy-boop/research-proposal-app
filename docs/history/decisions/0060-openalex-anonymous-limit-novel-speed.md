# ADR 0060 — OpenAlex 익명 검색 제한은 기다리지 않고 건너뛰고, novel 과제안은 확인·유추를 동시에 돌려 단계별로 보낸다 (2026-11-09, feat/wave-a-openalex-novel-speed)

## 맥락
- 2026-11-05 운영에서 ② novel 갈래의 넓힌 실시간 검색 중 OpenAlex 가 "오류"(`unavailable status=error`)로 표시됐다.
  운영 로그에는 `live.source_failed source=openalex err=RateLimited` 와 `err=LocalProtocolError` 두 줄, 야간 적재 로그에는
  `[openalex] 실패: RateLimited`. 실호출(2026-11-09)로 확인한 원인: OpenAlex 가 **익명(API 키 없음) 검색 요청을 혼잡할 때
  HTTP 429 `Retry-After: 30`** 으로 막고("Anonymous search is temporarily rate-limited … use a free API key"), 키 없는 요청은
  같은 공인 IP 가 하루 예산을 나눠 쓴다(응답 `meta.notice`, `x-ratelimit-limit: 1000`). `.env` 에는 `RRA_OPENALEX_API_KEY`·
  `RRA_OPENALEX_MAILTO` 가 없다. `LocalProtocolError` 는 httpcore(1.0.9)가 요청을 보내는 길(`_send_event`)에서 `h11.LocalProtocolError`
  를 감싸지 않아 `httpx.TransportError` 로 잡히지 않고 그대로 올라온 것(깨진 풀 연결, 재시도 없이 실패).
- GuardedClient 는 429 의 Retry-After 가 `max_backoff_sec`(30) 이하면 그만큼 자고 다시 보낸다 — 실시간 검색의 자료원 제한 시간
  (10·15초)보다 길어 결국 timeout 으로 끝나고, 31초면 즉시 RateLimited. 어느 쪽이든 OpenAlex 는 빠지고 다른 자료원까지 기다렸다.
- novel 과제안은 98.9초(운영 2026-11-05 측정) — 넓힌 실시간 검색(wait 25초) → ② 규칙 판정 재실행(reranker) → 유추 검색(실시간 25초
  + 저장 자료) → Argon 작성이 모두 순차였다. 목표 p50 60초 이하.

## 선택지
1. OpenAlex: Retry-After 만큼 기다린다(지금) — 실시간 검색은 어차피 제한 시간에 걸린다.
2. OpenAlex: 익명 429 는 기다리지 않고 그 자료원만 건너뛰며 안내(키 등록)를 남긴다. 야간 적재는 기다렸다 다시 보낸다.
3. 속도: 새로움 확인과 유추 검색을 순차로 두고 설정값(대기 시간)만 줄인다.
4. 속도: 새로움 확인 ∥ 유추 검색 ∥ 참고 논문 읽기를 동시에 돌리고, 넓힌 검색이 DB 에 새 문서를 넣었을 때만 규칙 판정을 다시 돌린다.
   다른 분야 사례가 준비되면 SSE 로 먼저 보낸다.

## 결정
2 와 4.
- **실시간 OpenAlex**(`adapters/sources/live.LiveOpenAlex`): 429 대기 상한을 5초로 줄여 Retry-After 30 은 즉시
  `SourceRateLimited`(`domain/rules/source_limits.py`) 로 올리고, `live_search` 는 그 자료원만 `error` + 안내("OpenAlex 가 익명(API 키
  없음) 검색을 제한함 — API 키(RRA_OPENALEX_API_KEY) 등록 필요")로 남긴다(coverage 열거값은 계약 그대로 `error`). 앞 질의에서 받은
  문서는 살린다. 야간 적재의 OpenAlexSource 는 `sources.yaml openalex.max_backoff_sec: 60` 으로 Retry-After 30~31 을 기다렸다 다시 보낸다.
- **GuardedClient**: `h11.LocalProtocolError` 를 전송 오류(`TRANSPORT_ERRORS`)로 다뤄 새 연결로 재시도한다(httpcore 가 그 연결을 닫는다).
- **근본 해결은 사람 몫**: OpenAlex 무료 API 키를 받아 `.env RRA_OPENALEX_API_KEY` 에 넣는다(요청 파라미터로만 실린다, 보안 D).
  키가 있으면 익명 제한·IP 공유 예산을 받지 않는다.
- **novel 과제안**(`usecases/recommend_projects`): 새로움 확인·유추 검색·참고 논문 읽기를 `asyncio.gather` 로 동시에(자료원별
  제한 시간은 LiveSearch 설정 그대로). 한 협력자의 실패는 그 협력자만 빠지고(coverage `unavailable`·사례 없음), `BudgetExhausted` 면
  나머지를 취소하고 올린다. 되돌림(새 차단 행)이면 유추 결과는 버린다. `WideNoveltyCheck` 는 넓힌 검색이 DB 에 **새로 저장한 문서**
  (`LiveSourceResult.new > 0`)가 있을 때만 ② 규칙 판정을 다시 돌린다 — 이미 있던 문서는 ② 가 같은 검색으로 이미 보았다.
- **단계 SSE**(`entrypoints/api/progress_routes.register_recommend_stream`, `POST /v1/precheck/recommendations/stream`):
  `stage`(search started → generate started, 되돌림이면 search reverted) → `analogies`(coverage + 다른 분야 사례, 최종 응답과 같은 칸
  모양) → `recommendations`(기존 POST 응답 본문 그대로) → `end`. 오류는 `error`(409 일일 상한·500) 뒤 `end`. 5초마다 `: keep-alive`.
  기존 POST 응답 형식(계약 5절)은 바뀌지 않는다. app.py 연결은 통합 때 메인이 한다(공용 파일).
- **측정 줄** `cache/recommend_metrics.jsonl` 에 `seconds_search`·`seconds_analogy`·`seconds_generate`(float|null) — 옛 줄에는 없고
  읽는 쪽(`rra feedback stats`)은 있는 줄만 중앙값을 낸다.

## 결과
- 좋은 점: OpenAlex 가 막혀도 실시간 검색 전체가 그 자료원 제한 시간을 기다리지 않는다. novel 과제안은 확인·유추가 겹쳐 돌아
  대기 시간이 큰 쪽 하나만 남고, 화면은 사례를 먼저 받을 수 있다.
- 비용: 되돌림(새 차단 행)일 때 유추 검색 호출이 헛돈다(실시간 검색 1회). 규칙 판정 생략은 "DB 에 이미 있던 문서는 ② 가 보았다"는
  전제 — ② 가 실시간 검색이 끝나기 전에 판정했고 그 문서가 넓힌 검색에서 다시 왔을 때는 다시 보지 않는다(드문 경우, 메모 30분).
- 수치(전후 p50·p90, OpenAlex 결과 수)는 `docs/status.d/feat-wave-a-openalex-novel-speed.md`·연표 조각에 적는다.
