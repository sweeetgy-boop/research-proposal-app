# fix/similar-count-rule (2026-11-04, ADR 0054) 전달 사항

## 전달한 것
- **한 규칙** 행의 유효 선택은 제안자 선택이고, 선택이 없으면 AI 같음 판정의 기본 선택이다(같다·일부 겹침 → [유사함], 다르다 → [관련 없음]).
  선택도 AI 판정도 없는 행은 [유사함] 이 아니다. 순수 규칙은 `domain/rules/similar_choice.effective_choice`·`effective_similar`·`default_choice` 에 있다.
  입구는 `application/usecases/similar_rows` 의 `similar_rows`·`similar_count`·`no_similar`·`basis_rows`·`default_choice_list`·`differentiation_rows` 다.
- **쓰는 곳** REST `similar_count`·`default_choices`·stage=full 활용 제안 조건, 과제안 '새 영역' 다시 받기·비교 대상, 비교표 [유사함] 열,
  활용 제안 대상이 모두 이 입구를 거친다. CLI·MCP·Streamlit 은 같은 유스케이스로 이 입구를 탄다.
  `similar_alerts` 와 `_choice_view` 의 직접 세기는 지웠다.
- **REST** `/v1/precheck/comparison`·`/v1/precheck/differentiate` 는 지금 AI 판정을 근거로 쓴다(`_current_alerts`, 진행 중이면 기다린다).
- **웹** 기본 선택 안내에 [유사함] 줄을 더했다. 지운 선택은 AI 기본 선택으로 돌아간다. [선택 적용] 전 활용 제안 건수는 기본 선택으로 센다.
- **변하지 않은 것** 차단 게이트(제안자 [관련 없음] 만 해제), 선택 기록(요청 선택만), 응답 필드 이름.
- **가짜 모드** 아이디어에 "(추천 없음)" 이 있으면 같음 판정이 모두 '다르다' 다(유사함 0 장면 유지).

## 시험
- pytest +20: 규칙 표 시험, 네 진입점 비교, 다시 받기 조건, 골든셋 03.
- vitest 는 기존 시험을 고쳤다(기본 선택 [유사함], 지우면 기본 선택으로).
- e2e spec 4개를 고쳤다: precheck-v3·precheck-flow·u9 에서 미리 고른 [유사함] 을 확인하고, precheck-series 의 건수를 "유사함 2건"(미리 고른 1 + 연작 행 1)으로 바꿨다. "유사한 과제를 고르면" 문구는 이제 첫 화면에
  나오지 않는다(AI 가 '같다'·'일부 겹침' 으로 본 행이 있으면).

## 남은 것
- 웹에서 미리 고른 값과 직접 누른 값은 선택 기록에서 구분되지 않는다(종전과 같다). 구분이 필요하면 요청에 출처 필드가 있어야 한다.
