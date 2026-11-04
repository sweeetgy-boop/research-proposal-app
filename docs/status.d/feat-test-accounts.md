# feat/test-accounts (2026-11-04, ADR 0056 덧붙임) 전달 사항

## 전달한 것
- **시험 계정 표시** `rra auth staff add --test`(getpass) — 사번 HMAC 을 `staff.json` 의 `test_hmacs` 에도 넣는다(`hmacs` 의 부분집합, 원문 없음,
  700/600 그대로). 키가 없는 옛 파일은 시험 계정 0건. `remove` 는 표시도 지운다. 일괄 등록 `--replace` 로 빠진 사번은 표시도 빠진다.
  이미 일반 사번으로 등록된 값에 `--test` 를 붙이면 표시를 바꾸지 않고 안내만 한다(실제 직원 사번 보호 — remove 뒤 add --test).
- **출력** `count`·`add`·`remove`·`import` → `등록된 사번: 83건 (시험 계정 1건)`, `status` → `직원 사번 등록: 83건 (활성, 시험 계정 1건), …`,
  `check` → `등록됨` | `등록됨(시험 계정)` | `미등록`.
- **세션** `Principal.test: bool = False`(domain), `auth_policy.staff_principal(digest, test=)`, `AuthStorePort.add_staff(…, test=)`·`is_test_staff(digest)`·
  `test_staff_count()`, `Login.staff` 가 채운다. 응답(`POST/GET /v1/session`)·화면에는 내보내지 않는다(칩 없음). 공용 계정·관리 토큰은 늘 False.
- **선택 기록** `similar_choice.choice_records(…, test=)` → 줄마다 `"test": true`(그 밖의 줄은 키 없음), `choice_log.ALLOWED_KEYS` 에 `test`.
  REST `_record_choices` 가 `_who(request).test` 를 넘긴다. 서명·세션 키는 그대로라 중복 한 줄 규칙이 같이 돈다.
- **과제안 측정** `RecommendProjects.__call__(…, test=False)` → `metrics_row(…, test=)` → 줄 끝 `"test": true`(`recommend_metrics.OPTIONAL_FIELDS`).
  REST 의 두 호출 자리(`_recommend`, `/recommendations/more`)가 시험 세션일 때만 `test=True` 를 넘긴다(`_test_kwargs`). 유스케이스·도메인은 세션을 모른다.
- **집계** `rra feedback stats [--include-test]` — 규칙 `domain/rules/feedback_stats`, 포트 `FeedbackReaderPort`·`JsonlRows`, 어댑터
  `adapters/logging/feedback_reader`(읽기만, O_NOFOLLOW, 측정 `.1` 포함, 폴더를 만들지 않음), 유스케이스 `usecases/feedback_stats`, 조립 `build_feedback_stats`.
  출력은 개수뿐(doc_id·해시·시각 없음, 열거값 밖은 "기타", 키 없음은 "없음"). 기존에 두 파일을 평가에 읽는 코드(`tools/`·`rra eval`·`usecases/evaluate`)는 없었다.
- **문서** ADR 0056 한 줄, architecture §4.14 측정 파일, pilot-guide §6.1·§6.3(배포 뒤 임시 사번은 `add --test`), deploy/README §4.5, `tools/deploy.sh` 끝 안내 한 줄.

## 시험
- pytest 2557 → 2571(+14): 저장소 표시·개수·삭제·옛 파일·일괄 교체·권한·원문 없음, 로그인 `principal.test`(파일 저장소·fake), 가짜 저장소, 기록 줄·측정 줄
  규칙·파일, REST 시험 세션 apply·generate·과제안(initial·more) 줄 `test: true`·일반/관리 세션 키 없음·응답에 표시 없음, 집계 규칙·유스케이스,
  CLI `auth staff add --test|count|check|status|remove`(임시 데이터 폴더 전체에서 사번 원문 검색)·`feedback stats`(기본 제외·`--include-test`·파일 무변경·파일 없음).

## 남은 것
- 이미 손으로 지운 30줄 외에 표시 없이 남은 옛 시험 줄은 구분할 수 없다(이 기능 이후 줄부터 표시).
- 화면 "시험 계정" 칩은 넣지 않았다(필요하면 `GET /v1/session` 에 필드 추가 → openapi 변경).
