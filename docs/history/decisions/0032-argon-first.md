# ADR 0032 — 초안은 Argon 이 먼저 쓰고, 실패 섹션만 로컬 모델이 쓴다 (2026-10-28)

## 배경
ADR 0007(로컬 작성 + 외부 검토)·0027(로컬 실패 섹션만 Gemini 대체 작성)로 시범을 준비했지만, 7B 로컬 작성은 한 건에
150초 이상 걸리고(실측 227초 중 생성 155초) JSON 실패가 잦았다(10건 중 4). 그동안 생성 동시성 1(보안 G)이라 3명이 동시에
쓰면 대기가 길다. 소유자가 2026-10-28 다음을 승인했다: 시범 기간 섹션 작성을 Gemini 4 Argon 이 먼저 하고, 직원 계정은
public+internal 근거를, 공용 계정은 public 만 보낸다. 화면에 전송 안내 문구는 넣지 않는다.

## 선택지
1. 그대로(로컬 먼저) — 시간·형식 실패가 그대로.
2. **Argon 먼저, 실패 섹션만 로컬** — 작성·검색·규칙은 그대로 두고 작성자만 바꾼다. 로컬 모델은 대체 작성·근거 대조에만.
3. Argon 만(로컬 없음) — 키·예산·429 가 막히면 빈 초안. ADR 0027 의 "빈 초안 금지"에 어긋난다.

## 결정
2 를 `llm.yaml compose.writer: gemini` 로 켠다(`local` 이면 예전 흐름, 키가 없으면 자동 local).

- 작성: 검색·본보기·작성 규칙·JSON 스키마·교정 재요청 1회는 같다. 한 run 안에서 섹션을 `compose.concurrency`(4)개씩 동시에.
  Q7 두 후보는 pipeline 설정 그대로(끔).
- 로컬 대체: Argon 호출 실패(`error`), 429 재시도 소진(`rate_limit`, 어댑터가 포트 예외 `RateLimited` 를 던진다), 일일 예산
  (`budget`, BudgetExhausted), 교정 재요청 뒤에도 무효(`invalid`)인 섹션만 로컬 모델이 쓴다. 로컬 실패는 ADR 0027 대로 실패 섹션.
- 기록: `RunState.writers[key] = {provider, model, local_fallback, reason, public_doc_ids, internal_doc_ids, calls}` — manifest
  `writer`·`writers`·`local_sections`·`gemini_calls`(compose·review·figures·total), 화면은 provider·model·local_fallback·reason 만.
- 보안 A: Argon 문장의 근거 id 는 "보여 준 청크" 집합과 대조한다(ADR 0027 대체 작성과 같다).
- 전송 범위: 직원 run = `external_llm.include_internal`(true), 공용 계정 run = PublicOnlyRepository 스냅샷 + 원격 프롬프트에서
  internal 청크·본보기 제외(이중 방어).
- 1차 검토: Argon 이 쓴 초안을 Argon 이 다시 보면 자기 검토라 `review.first_pass: off` — draft_review 단계를 계획에서 빼고
  `draft_review_skipped = self_review`. ⑤ 최종 검토는 Argon 그대로이며 그 뒤 마무리한다(review_skipped 아님). 가짜 모드는
  e2e 화면을 위해 1차 검토를 켠 채로 둔다.
- 로컬 근거 대조 `compose.local_check`(기본 끔): Argon 이 쓴 섹션의 근거 있는 문장을 로컬 모델이 지지|부분|불일치로만 판정,
  섹션당 20초 상한(넘으면 건너뜀·기록), 불일치는 `local_evidence_mismatch` 경고(문장 글자 해시로 기억 — 고치면 사라진다).
- 동시성(보안 G 완화, Argon 작성 한정): run 은 `config/runs.yaml max_concurrent`(3)칸 FlockPool(`runs/.run-<i>.lock`)만 잡고,
  로컬 모델 단계(대체 작성·local_check·설계도)만 기존 FlockSlot(`.generate.lock`)을 잡는다. 임베딩 계산은 프로세스 안
  락으로 직렬화(MPS), SQLite 는 기존 RLock, reranker 는 기존 락. 로컬 작성이면 예전처럼 run 전체가 슬롯 1칸 안.
- 예산: `budget.gemini_daily_calls` 300 → 600.

## 이유
- 작성 시간·형식 실패가 가장 큰 불만이고, 검색·검증·규칙 정리는 그대로라 품질 장치를 잃지 않는다.
- 실패를 섹션 단위로 로컬에 넘겨 외부 장애·예산 소진에도 빈 초안이 나오지 않는다(ADR 0027 유지).
- 로컬 모델이 한 번에 하나만 돌면 24~32GB 기기의 메모리 위험은 예전과 같다.

## 결과
- 실측(골든셋 01, 3개 섹션, 2026-10-28): 섹션당 6.6~11.8초, 3개 동시 벽시계 11.8초, 교정 재요청 0, 로컬 대체 0, Gemini 3회.
- ADR 0007 의 "작성 = 로컬"은 시범 기간 `compose.writer` 로 바뀐다(되돌리기 = `writer: local`, `first_pass: on`).
- 남은 것: 골든셋 10건 `rra eval` 재측정(점수·인용·시간), local_check 효과 측정 뒤 기본값 결정.
