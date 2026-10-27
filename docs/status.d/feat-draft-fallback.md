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
