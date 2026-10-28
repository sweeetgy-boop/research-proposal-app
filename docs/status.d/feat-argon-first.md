# 레인 B — feat/argon-first (2026-10-28, [3] 초안 작성 순서 변경) 전달 사항

## 전달한 것
- **Argon 먼저 작성** `llm.yaml compose.writer: gemini`(키 없으면 자동 local, `local` = 예전 흐름). 섹션 4개씩 동시
  (`compose.concurrency`). 실패(error·rate_limit·budget·invalid) 섹션만 로컬 모델이 FlockSlot 을 잡고 쓴다. ADR 0032.
- **기록** `RunState.writer`·`writers`·`local_check`, manifest `writer`·`writers`·`local_sections`·`local_check`·`gemini_calls`
  (허용목록 갱신), `UsageRecord.gemini_calls`, `rra eval` EvalIdea `writer`·`local_sections`·`compose_calls`·`gemini_by_stage`.
- **API** GET /v1/runs/{id}/draft: `writers`·`local_sections`·`local_check`. GET /v1/runs/{id}: `writer`·`local_sections`.
- **1차 검토 끔** `review.first_pass: off` → `draft_review_skipped = self_review`(단계 계획에서 빠짐). 최종 검토·마무리 그대로.
  가짜 모드(RRA_FAKE_LLM)는 e2e 화면 때문에 1차 검토를 켠 채로.
- **local_check**(기본 끔) 지지|부분|불일치, 섹션당 20초, 불일치 → `local_evidence_mismatch` 경고.
- **동시 생성** `config/runs.yaml max_concurrent: 3`(FlockPool), 로컬 단계만 `.generate.lock`. 임베딩 encode 락. 429 → `RateLimited`.
- **예산** `budget.gemini_daily_calls` 600.

## 자동 결정
- 원격 작성이면 ADR 0027 대체 작성(로컬 실패 → Gemini)은 조립에서 끈다(역할이 뒤집힘).
- 로컬 대체 섹션도 원격에 보낸 적이 있으면 전송 doc_id·호출 수를 남긴다(예산 소진은 0·빈 목록).
- 그림 단계 호출(`_figures_step`)은 Argon 작성일 때 로컬 슬롯 안에서 돈다(명세가 로컬 모델) — 레인 A 가 명세를 Argon 으로 옮기면 걷어낸다.
- 검토(⑤)는 Argon 작성일 때 전역 슬롯 대신 run 칸(FlockPool)을 잡는다.

## 남은 것
- 골든셋 10건 재측정(`rra eval`)과 local_check 효과 측정 → 기본값 결정.
- 웹 e2e `flow.spec.ts` 는 가짜 모드 1차 검토를 그대로 기대하므로 손대지 않았다(가짜 모드 first_pass 켬).
