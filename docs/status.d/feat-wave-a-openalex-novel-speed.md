# feat/wave-a-openalex-novel-speed (2026-11-09, 레인 A, ADR 0060) 전달 사항

## 전달한 것
- **OpenAlex 실시간 "오류" 원인** — OpenAlex 가 익명(API 키 없음) 검색을 혼잡 때 HTTP 429 `Retry-After: 30` 으로 제한(실호출 확인,
  fixture `tests/fixtures/openalex/rate_limited_429.json`). 운영 두 번째 오류 `LocalProtocolError` 는 httpcore 가 감싸지 않는
  `h11.LocalProtocolError`(깨진 풀 연결)가 그대로 올라온 것.
- **고친 것** `LiveOpenAlex` 429 대기 상한 5초 → `SourceRateLimited`(`domain/rules/source_limits.py`) → 실시간 검색은 그 자료원만
  `error` + 안내("… API 키(RRA_OPENALEX_API_KEY) 등록 필요"), 앞 질의 결과는 살림. `GuardedClient` 는 h11 LocalProtocolError 를 전송
  오류처럼 재시도. `sources.yaml openalex.max_backoff_sec: 60`(야간 적재는 기다렸다 다시). 실응답 fixture `works_pigeon.json`(12건, 이름 제거).
- **novel 과제안 속도** 새로움 확인 ∥ 유추 검색 ∥ 참고 논문을 동시에(`asyncio.gather`, 자료원별 제한 시간 그대로, 부분 실패는 그
  협력자만), 넓힌 검색이 새 문서를 넣었을 때만 ② 규칙 판정 재실행. 진행 콜백 `progress(stage|analogies)`.
- **단계 SSE** `POST /v1/precheck/recommendations/stream`(`progress_routes.register_recommend_stream`): `stage` → `analogies`(사례 먼저)
  → `stage` → `recommendations`(기존 응답 그대로) → `end`, 오류 `error`, 5초 `: keep-alive`, 끊으면 취소. **app.py 연결은 통합 때**(PR 설명).
- **측정 줄** `cache/recommend_metrics.jsonl` 새 칸 `seconds_search`·`seconds_analogy`·`seconds_generate`(float|null, 옛 줄 없음),
  `rra feedback stats` 에 갈래·단계 중앙값 줄(cli.py 변경 없음).

## 측정 (비둘기 사례, 2026-11-09 14:40~15:13, 실제 Argon·실제 자료원, `RRA_DATA_DIR` 원 저장소)
- 방법: 전 = 운영 API(2c7497f, 127.0.0.1:8000, HTTP) / 후 = 이 브랜치 `build_api` 를 프로세스 안(ASGI, 측정 줄은 메모리 sink)에서.
  비둘기 아이디어를 표현만 다르게 쓴 변형 6개(각 arm 3개, 모두 콜드 — 키워드·검색 캐시·메모 없음), 전/후 교대. 순서:
  `POST /v1/precheck?stage=rule` → 모든 행 [관련 없음] 선택으로 `POST /v1/precheck/recommendations`(이 호출만 잼; 안에 `current()` 의
  AI 판정 합류 ~10초 포함 — 웹은 판정을 따로 부르므로 실제 체감은 "유스케이스 초"에 가깝다).
- 조건 차이(해석에 주의): 다른 레인 pytest·평가가 같은 기기에서 돌아 load 2.5~9(전 v0 은 load 7.9, 229.9초). 운영 API 의 ScienceON 주 세션이
  v2·v4 에서 즉시 error(0건)라 넓힌 검색이 빨리 끝났고, 후 arm 은 ScienceON 이 29~45건 정상 수신(일을 더 함). 후 v5 에서 OpenAlex 익명 429 가
  실제로 왔고 새 코드가 기다리지 않고 건너뛰어(`live.rate_limited`) search 14.9초로 끝났다.

| | 전(운영, 3회) | 후(이 브랜치, 3회) |
|---|---|---|
| 과제안 호출 전체 초 | 229.9 · 61.7 · 72.8 → **p50 72.8 · p90 198.5** | 69.7 · 81.3 · 65.2 → **p50 69.7 · p90 79.0** |
| 유스케이스 초(측정 줄 `seconds`) | 213.6 · 52.7 · 62.5 → p50 62.5 · p90 183.3 | 60.2 · 67.8 · 54.8 → **p50 60.2 · p90 66.3** |
| 단계(후만, 중앙값) | — | search 19.0(∥) · analogy 13.3(∥) · generate 28.5 |
| 갈래·카드 | novel 3/3, 카드 2·1·2 | novel 3/3, 카드 2·2·2 |

- 목표(p50 60초 이하)는 유스케이스 기준 경계(60.2), 호출 전체 기준 미달(69.7 — 판정 합류 10초 포함). 동시 실행으로 유추 검색 시간(≈13초)이
  전부 겹쳐 사라졌고, 넓힌 검색 뒤 규칙 판정은 새 문서가 있을 때만 돈다. 남은 큰 덩어리는 Argon 작성(26~32초)과 ScienceON 넓힌 검색
  (질의 5 × target 3, 초당 1회 ≈ 15초) — 후자는 `config/novelty.yaml novelty.live.max_queries` 를 줄이면 더 빨라지나 확인 범위가 좁아진다(결정 대기).
- **OpenAlex 실시간 결과 수(비둘기, 후 arm)**: 주 실시간 검색 0·30·30건(v3 는 영문 키워드 없음), 넓힌 검색 40·40·0건(v5 는 익명 429 → error),
  유추 검색 30·30·30건. 전 arm 운영 API 주 세션은 30·30건(v2·v4). 2026-11-05 운영 당시 "오류"는 같은 429 였다.
- 측정 줄: 운영 파일에 전 arm 3줄이 실제 호출로 남았다(14:44·15:04·15:10, 관리자 세션 — `test` 표시 없음). 후 arm 은 파일에 쓰지 않았다.

## 사람 할 일
- OpenAlex 무료 API 키 발급 → `.env RRA_OPENALEX_API_KEY=`(+ `RRA_OPENALEX_MAILTO=`) → API 재시작. 키 없이는 혼잡 때마다 OpenAlex 실시간이
  빠진다(이제는 기다리지 않고 바로 건너뛰며 안내가 남는다).
- 통합: app.py 연결 4곳(PR 설명 코드 조각) · `rra api schema` 재생성 · 웹(레인 B) 은 `stream` 이벤트로 사례 먼저 표시.

## 남은 것
- 되돌림(새 차단 행)일 때 유추 검색 1회가 헛돈다(동시 실행의 비용). 규칙 판정 생략은 "DB 에 이미 있던 문서는 ② 가 보았다" 전제.
- OpenAlex 키가 들어오면 `rra sources check` 에 키 유무·익명 제한 진단을 더하는 것이 좋다(이번 범위 밖).
