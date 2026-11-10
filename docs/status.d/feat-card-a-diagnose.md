# feat/card-a-diagnose (2026-11-10, ADR 0065 레인 A) 전달 사항

## 전달한 것
- **진단** `application/usecases/diagnose_problem.DiagnoseProblem` — 설정 꺼짐이면 `status="off"`, Argon 1회(형식 오류면 교정 1회, 오류 응답일 때만 로컬),
  `timeout_seconds` 넘으면 `failed`/`timeout`. 분류 코드는 코드마다 함께 확인(5초 넘으면 확인 못 함).
- **규칙** `domain/rules/problem_card.py`(파싱·검증·근거 판정·문제어 정리·원인 불일치·사용자 항목 보존·수정 반영·화면 4줄)·`triz.py`(40 원리 고정 목록)·
  `card_edits.py`(수정 짝·다듬기 판정·본인 예시 고르기·card_edit 줄).
- **수정 반영** `usecases/edit_problem_card.EditProblemCard` — 고친 항목만 origin=user, 기대는 것만 다시 계산. 공용 계정은 기록하지 않는다.
- **어댑터** `adapters/classification`(저장 자료 코드 건수 → KIPRIS 건수 자리, 코드별 캐시), `adapters/logging/card_edit_log.py`(600/700, 허용 칸),
  저장소 `count_by_code`·`count_by_science_class`, 프롬프트 `diagnose.md`, 가짜 모드 진단 응답.
- **REST** `entrypoints/api/problem_card_routes.register` — `POST /v1/ideas/diagnose`·`/v1/ideas/diagnose/edit`. `app.py` 연결은 통합 때.
- **조립** `composition.build_problem_diagnosis`·`build_card_editor`·`build_card_edit_log`·`build_class_code_check`.

## 남은 것
- `app.py` 등록·`build_api` 연결(PR 본문의 코드 조각), `docs/openapi.json`·`web/src/api/schema.d.ts` 갱신.
- 레인 B 의 `PatentClassCount` 를 `class_count=` 로 넘기기(지금은 저장 자료로만 확인).
- 스위치는 꺼짐 — 4사례 실제 카드를 소유자가 확인한 뒤 켠다.
