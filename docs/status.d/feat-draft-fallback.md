## [F1] 빈 초안 금지·원인 표·대체 작성 (feat/draft-fallback, 2026-10-28)

### 1. invalid run 원인 표 (저녁 측정 final10_review·retry 15건 + 시범 흐름 01, run 폴더의 manifest/steps·sections·context 로 복원)

| 골든셋 | run | 실패 단계·섹션 | parse / raw_chars / 재요청 | 원인 분류 | 섹션 프롬프트 [자료] (청크 수 / 글자) |
|---|---|---|---|---|---|
| 01 | final10 6674636c | tech_importance·expected_technology·expected_standing | json 2046 / json 497 / json 485, 각 1회 재요청 실패 | JSON 깨짐(2046자는 compose max_tokens 2000 근처 → 잘림 의심) | 13 / 9,162·8,649·8,638 |
| 01 | retry 79aa0aac | expected_standing | json 526 | JSON 깨짐 | 13 / 8,638 |
| 01 | 시범 587154f0 | strategy_alignment·expected_technology·expected_standing | fence 326 / json 557 / json 508 | 펜스 밖 설명문 1 + JSON 깨짐 2 | 13 / 8,649·8,638 |
| 02 | final10 f255b1d7 | task_type | **ok** 302, 문장 0(choices=applied 만) | **스키마 불일치(허용된 빈 목록)** — `sentences` 가 없거나 비어 ok 로 통과 → 필수 섹션 missing → invalid. parse_failed 로그 없음 | 기본 집합 20 / 19,608 |
| 02 | retry 12201bcb | title·task_type | ok 191 / ok 300, 문장 0 | 같은 원인(빈 목록 ok) | 20 / 19,608 |
| 05 | final10 c5cd9b58 | title (+strategy_alignment 문장 0, 선택지만) | ok 425, 문장 0 | 빈 목록 ok (title 은 choices 모양 `{"sentences": []}` 추정) | 20 / 16,136 |
| 06 | final10 c605c7f6 | title·tech_importance·expected_standing | json 431 / json 679 / json 245 | JSON 깨짐 (짧은 응답 — 잘림 아님, 따옴표·쉼표 오류) | 20 / 16,136 · 8 / 2,960 · 8 / 4,737 |
| 06 | retry ab451014 | expected_standing | json 264 | JSON 깨짐 | 8 / 4,737 |
| 10 | final10 384a0539 | title·task_type | ok 201 / ok 201, 문장 0 | 빈 목록 ok. parse_failed 로그 없음 | 20 / 20,602 |
| 10 | retry d4985b58 | title·task_type | ok 201 / ok 198, 문장 0 | 빈 목록 ok | 20 / 20,602 |
| 07 | final10 48fb6e83 (drafted) | strategy_alignment | json 3043 | 잘림 의심(3,043자) — 필수 아님이라 경고만 | 20 / ~20k |

- 분류 합계(실패 섹션 23건): JSON 깨짐 11, 펜스 2, **빈 목록이 ok 로 통과 10** (02·05·10 전부, "다른 원인"의 정체).
  출력 잘림(max_tokens)은 raw_chars 2,046·3,043 두 건만 의심(usage 에 finish_reason 기록이 없어 확정 불가 → 어댑터가
  finish_reason=length 를 로그·집계하도록 [2]에서 보강). 입력 길이 초과(prompt_max_chars 120,000)는 없음.
- **프롬프트 길이 비교(같은 골든셋 01)**: 오전 all4(코퍼스 ≈5,800, 11:52, 유효) 섹션 [자료] 13청크 4,166~4,504자, 기본 집합 25청크
  12,974자 → 저녁(코퍼스 11,008) 같은 13청크인데 **8,416~10,043자(2.1×)**, 기본 집합 25청크 22,211자(1.7×). 청크 수는 같고 청크가
  길어졌다(공사 홈페이지·PDF 긴 청크). 제목·선택형은 기본 집합(20~25청크, 16~22k 자)을 그대로 받는다 → 7B 가 JSON 을 못 지킴.
- 원인별 대책([2]): (a) 빈 목록을 필수 섹션에서는 실패로 보고 교정 재요청 → 그래도 비면 실패 섹션. (b) 섹션 프롬프트 청크 글자 상한
  (`pipeline.yaml chunk_max_chars`)·제목·선택형 기본 집합 청크 수 상한(`base_chunk_limit`). (c) finish_reason=length 로그.
  (d) 그래도 실패한 섹션만 Gemini 대체 작성([3]).

### 2. 빈 초안 금지 (PR 1)
- `domain/rules/draft_failures.py`: step 기록만으로 실패 섹션(`fence|json|schema|choices_only|empty|dropped`) 판정,
  `missing` 오류 → `generation_failed` 경고, 전부 실패일 때만 invalid, 새 버전에서 채워지면 목록에서 제거.
- `RunState.failed_sections`(state.json·manifest `failed_sections` 허용목록), REST `GET /v1/runs/{id}`·`/draft` 에 `failed_sections`
  [{key, reason, label}], render-check notes "생성 실패 섹션 n개…", submit-check 항목 `failed_sections`. finalize 는 막지 않는다.
- 웹 초안 화면: 실패 섹션 머리에 "생성 실패" 배지 + [이 섹션 다시 생성](U3 `POST …/sections/{key}/rewrite` + apply 재사용) + 상단 요약 알림.
  Streamlit 은 목록 경고만. CLI `generate` 는 일부 실패면 EXIT_OK + `~ 섹션: generation_failed`, 전부 실패면 EXIT_INVALID.
- 기존 테스트 2건의 기대값 변경(invalid → drafted + failed_sections): `test_resume_keeps_the_original_evidence_set…`,
  `test_lint_failure_is_a_state_not_an_exception`, CLI `test_generate_lint_failure_exit_code`(전부 실패 케이스 추가).

### 3. 원인에 맞는 수정 (PR 2)
- **빈 목록 = 실패**(원인 표의 10건): `domain/rules/llm_output.is_empty_result` — 필수 섹션인데 parse ok 이고 문장 0 이면 실패로 보고
  `EMPTY_HINT`("sentences 가 비어 있었음 … 1개 이상")로 교정 재요청 1회. 그래도 비면 실패 섹션(`empty`) → 대체 작성.
- **섹션 프롬프트 [자료] 상한**(원인 표의 2.1×): `config/pipeline.yaml chunk_max_chars: 500`(청크 본문 글자, 넘으면 자르고 …),
  `base_chunk_limit: 10`(섹션별 검색이 없는 제목·선택형의 기본 집합 20~25 → 10). 규칙 `domain/rules/section_search.clip_chunks`
  (유사과제 #overlap 청크는 개수 상한에서 제외, 스냅샷·근거 대조 집합은 그대로). 적용 `GenerateProposal.chunks_for`.
  기대 글자: 섹션 13청크 ≤ 6.5k(이전 8.4~10k), 제목 10청크 ≤ 5k(이전 16~22k) — 오전 유효 측정(4.2k·13k) 사이.
- **잘림 추적**: 어댑터가 `choices[0].finish_reason == "length"` 를 세고(`OpenAICompatLLM.truncated`) `llm.truncated …` 경고를 남긴다
  (`_payload.extract_finish_reason`). compose max_tokens 는 2000 유지 — 2,046·3,043자 두 건만 의심이라 상한을 올리기보다 로그로 확정한 뒤 조정.

### 4. 대체 경로 — Gemini 대체 작성 (PR 2, ADR 0027)
- 설정 `config/llm.yaml stages.compose.fallback: gemini`(시범 기본 켬). `config_loader.llm_fallback` → `composition.build_compose_fallback`:
  providers 표에 없는 이름은 오류, 키(`RRA_GEMINI_API_KEY`) 없으면 경고 1줄 + 자동 끔. `build_llm(stage="compose", provider="gemini")`
  → BudgetedLLM(일일 예산 `budget.gemini_daily_calls` 카운터, 검토와 같은 파일).
- 동작(`GenerateProposal._compose_llm`): 로컬 첫 응답 실패(파싱 오류 또는 필수 섹션 빈 목록) → 로컬 교정 재요청 → 그래도 실패일 때만
  Gemini 1회(compact 프롬프트 = 설계도·본보기·후보 없이 기본 지시 + 같은 [자료]). `BudgetExhausted` → `fallback_error=budget`,
  네트워크·인증 예외 → 클래스명만, 응답 파싱 실패 → 그 상태. 전부 실패 섹션으로 남는다(PR 1 경로).
- 전송 범위 = 검토와 같다: `external_llm.include_internal`(false 면 internal 청크를 [자료] 에서 뺀다), 공용 계정 run 은
  `generate_public`(PublicOnlyRepository 스냅샷)이라 internal 이 애초에 없다. **근거 id 검증(보안 A)**: 대체 작성 문장의 evidence 는
  스냅샷 전체가 아니라 "보여 준 청크" 집합(+유사과제 doc_id)과 대조한다 — 보여 주지 않은 internal id·스냅샷 밖 id 는 폐기.
- 기록: `RunState.fallback_sections[{key, reason, provider, model, public_doc_ids, internal_doc_ids, calls}]`(본문 없음),
  `StepRecord.fallback="gemini/gemini-4-argon"`, manifest `fallback_sections`·step `fallback` 허용목록, 로그 `run.section_fallback`.
  REST run/draft 응답 `fallback_sections[{key, provider, model, reason}]`(doc_id 는 manifest 에만). 웹 초안 화면은 섹션 제목 옆
  "대체 작성" 배지만(title 에 provider/model). `rra eval` 은 아이디어별 실패/대체 섹션·`fallback_calls` 를 세고 `gemini_calls` 에 합산.
- 테스트: `tests/application/test_draft_fallback.py`(빈 목록 → 재요청 → 대체, 성공·선택 섹션은 대체 없음, 보여 준 청크 밖 인용 폐기,
  internal 포함/제외, 예산·네트워크·응답 실패, RunManager state/step/manifest/payload), `tests/domain/test_clip_chunks.py`,
  config_loader 2건(fallback 읽기·거부, 프로젝트 yaml 값), 어댑터 잘림 집계 1건.

### 5. 골든셋 10건 재측정 (2026-10-28 02:11~02:45, 코퍼스 11,008, 기본 파이프라인, 로컬 Qwen2.5-7B + 검토 Gemini)
`rra eval --label f1_fallback`(PR 2 코드) → `data/eval/f1_fallback.json`, 비교표 `docs/eval-2026-10-28.md`.

| | 저녁 final10_review(+retry) | **f1_fallback** |
|---|---|---|
| 유효 run | 6/10 (01·02·06·10 두 번 모두 invalid) | **10/10, invalid 0, 빈 초안 0** |
| 실패 섹션 / 대체 작성 | — | 1 (10 task_type: 파싱 ok 였지만 검증에서 전부 폐기) / 1 (05 tech_importance: 로컬 JSON 2회 실패 → Gemini) |
| 1차 점수 평균 (4항목) | 2.45 (유효 5건) | 2.77 (10건) |
| 충족률 / 논문 인용 / 무관 인용 | 0.63 / 2 / 0 | 0.67 / 3 / 0 |
| 문장 v1→v2 (합계) | 93→105 (5건) | 181→202 (10건) |
| precheck 적중 | 6/10 | 5/10 (이 레인 범위 밖, 변화 없음) |
| 평균 시간 | 179.8s | 201.2s (재요청·대체 작성 분) |
| Gemini 호출 | 5 | **11** (검토 10 + 대체 작성 1; 예산 카운터 11/300) |

- 01·02·06·10 이 전부 유효해졌고(제목·선택형의 기본 집합 10청크·청크 500자 + 빈 목록 재요청), 05 는 대체 작성으로 채워졌다.
  `parse_failed` 로그 0건(어제 15 run 에 13건) — 프롬프트 상한이 JSON 깨짐 자체를 줄였다. `llm.truncated` 0건.
- 남은 1건(10 task_type `dropped`): 모델이 문장을 냈지만 입력에 없는 고유명으로 전부 폐기 — 재요청·대체 조건이 "파싱 실패·빈 목록" 뿐이라
  걸리지 않았다 → 같은 PR 에서 "검증 뒤 문장 0" 도 실패로 보고 폐기 사유를 붙여 재요청(`dropped_hint`) → 대체 작성으로 확장.
  확장 뒤 재측정(`f1_fallback2`)은 아래 §6.
