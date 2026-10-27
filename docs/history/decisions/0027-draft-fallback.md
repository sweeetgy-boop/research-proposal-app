# ADR 0027 — 빈 초안 금지와 실패 섹션의 Gemini 대체 작성 (2026-10-28)

## 배경
2026-10-27 저녁 골든셋 10건 측정(코퍼스 11,008)에서 01·02·06·10 이 두 번 모두 `invalid`(초안 비어 있음), 시범 흐름 01 도 invalid.
run 폴더로 복원한 원인(docs/status.d/feat-draft-fallback.md §1): 로컬 7B 의 JSON 깨짐 11건·펜스 2건, 그리고 **빈 문장 목록이
ok 로 통과해 필수 섹션이 비는 경우 10건**. 한 섹션만 실패해도 `has_errors`(missing) 로 run 전체가 invalid 가 되어 성공한 11개
섹션까지 버려졌다. 내일 3명 시범에 빈 초안을 줄 수 없다.

## 선택지
1. 그대로 두고 시범 중 "다시 생성" 으로 대응 — 매번 3분, 같은 섹션이 다시 실패한다.
2. **실패 섹션만 빈칸으로 남기고 run 은 drafted 로 이어 간다(검토·편집 가능). 전부 실패일 때만 invalid.** 실패 섹션은 목록·사유를 남기고
   화면에서 그 섹션만 다시 생성한다.
3. 2 + 로컬 교정 재요청까지 실패한 섹션만 Gemini 4 Argon 이 작성한다(검토와 같은 전송 범위 규칙, 일일 예산 카운터, 근거 id 검증 동일).
4. 전부 Gemini 로 작성 — 외부 전송이 전 섹션으로 늘고 ADR 0007(로컬 작성 + 외부 검토)에 어긋난다.

## 결정
2 를 먼저(PR 1), 3 을 설정으로 켠다(PR 2, `llm.yaml compose.fallback: gemini`, 키 없으면 자동 끔). 4 는 하지 않는다.

규칙(domain/rules/draft_failures.py):
- 실패 판정은 step 기록만 본다(재개·재조회에 같은 답): parse ≠ ok → 그 사유, 필수 섹션인데 ok 이고 문장 0 → `empty`(폐기 있으면 `dropped`).
- 실패 섹션의 `missing` 오류는 `generation_failed` 경고로 바꾼다. 그 밖의 오류는 그대로(invalid 조건 유지).
- LLM 이 쓴 섹션 전부가 실패했을 때만 invalid(빈 초안).
- 새 버전에서 문장이 채워지면 목록에서 뺀다.
- 대체 작성(PR 2)은 실패 섹션에만, 전송 범위는 검토와 같다(`external_llm.include_internal`, 공용 계정 run 은 PublicOnlyRepository 스냅샷).
  manifest 에 섹션 키·사유·provider/model·전송 doc_id 만 남기고 본문은 남기지 않는다. 대체 작성 문장도 같은 근거 id 검증(보안 A)을
  거친다. 화면에는 "대체 작성" 배지만.

## 이유
- 빈 초안은 시범에서 가장 나쁜 결과다. 성공한 섹션을 보여 주고 실패 섹션만 고치게 하면 3분 재생성 없이 이어 갈 수 있다.
- 실패 판정을 step 기록에 두면 원문 저장 없이(보안 I) 재개·조회·manifest 가 같은 답을 낸다.
- 대체 작성을 "로컬 2회 실패 뒤에만" 으로 묶어 외부 전송을 최소화한다(ADR 0007 유지).

## 결과
- `RunState.failed_sections`, manifest `failed_sections`, REST/웹/Streamlit/CLI 표시, render/submit-check 경고. finalize 는 막지 않는다.
- 기존 테스트 2건의 기대값이 invalid → drafted 로 바뀌었다(의도된 동작 변경).
