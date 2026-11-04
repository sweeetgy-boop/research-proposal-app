# ADR 0054 — "유사함 0건" 한 규칙: 제안자 선택, 없으면 AI 판정의 기본 선택 (2026-11-04, fix/similar-count-rule)

## 맥락
- ADR 0053 결과에 '유사함 0건'의 뜻이 둘이라고 적었다. REST(similar_only)는 "[유사함] 으로 고른 행 없음",
  CLI·MCP·Streamlit 옛 경로는 "비교 대상 알림 없음"이었다.
- 규칙이 여러 곳에 흩어져 있었다.
  - `domain/rules/precheck_levels.default_choices`: AI '다르다' 행만 [관련 없음] 을 미리 고른다.
  - `domain/rules/similar_choice.similar_alerts`: 명시적으로 [유사함] 을 고른 행만.
  - `entrypoints/api/app._choice_view`: `similar_count` 를 명시적 선택만으로 직접 셌다.
  - `usecases/recommend_projects`: '새 영역' 다시 받기 조건을 모드마다 다르게 셌다.
  - `usecases/differentiate`·`compare_projects`: `similar_alerts` 를 따로 불렀다.
- 그래서 AI 가 '일부 겹침'으로 본 행이 있어도 제안자가 아직 고르지 않았으면 "유사함 0건"이 되었다. 과제안은 '새 영역' 지시로
  다시 받았고, 비교표는 비었으며, 활용 제안도 건너뛰었다.

## 선택지
1. 그대로 둔다. 진입점마다 뜻이 다르고, 고르지 않은 '일부 겹침'은 계속 0건으로 셈한다.
2. 명시적 선택만 센다(REST 규칙으로 통일). CLI·MCP·Streamlit 에는 선택 화면이 없으므로 그곳에서는 늘 0건이 된다.
3. **행의 유효 선택 = 제안자 선택, 없으면 AI 판정의 기본 선택**으로 한 규칙을 만들고 모든 진입점이 이 규칙을 거친다.

## 결정
3을 택한다(소유자 결정).
- 행이 [유사함] 인지는 제안자 선택으로 정한다. 선택이 없는 행은 AI 같음 판정의 기본 선택을 따른다. '같다'·'일부 겹침'은 [유사함],
  '다르다'는 [관련 없음] 이다. 선택도 AI 판정도 없는 행(규칙 판정·AI 실패·판정 전, `judged_by=rule`)은 [유사함] 이 아니다.
- 순수 규칙은 `domain/rules/similar_choice` 에 둔다: `default_choice`·`effective_choice`·`effective_similar`.
  `precheck_levels.default_choices`·`basis_alerts` 도 이 규칙을 쓴다.
  모든 진입점의 입구는 `application/usecases/similar_rows` 하나다.

  | 함수 | 쓰는 곳 |
  |---|---|
  | `similar_rows` | 비교표 [유사함] 열 |
  | `similar_count` | REST `similar_count`, `/v1/precheck` stage=full 의 활용 제안 실행 조건 |
  | `no_similar` | '새 영역' 다시 받기 조건(과제안 유스케이스 안에서) |
  | `basis_rows` | 과제안 비교 대상 |
  | `default_choice_list` | REST `default_choices` |
  | `differentiation_rows` | 활용 제안 대상 |

- 과제안('새 영역' 다시 받기 포함)·활용 제안은 유스케이스 안에서 이 함수를 부른다. 그래서 REST·CLI(`rra recommend`·`rra differentiate`·
  `rra precheck` 자동)·MCP(`rra_recommend`·`rra_differentiate`)·Streamlit(ProposalAssistant)이 같은 규칙을 쓴다.
- 과제안 유스케이스는 모드와 상관없이 `req.choice_map()` 과 같은 규칙을 쓴다. 선택도 AI 판정도 없는 알림이면 `basis_rows` 가 알림
  전부를 돌려준다. 옛 경로의 비교 대상은 그대로다.
- 활용 제안: REST(선택 화면)는 [유사함] 행만 쓴다. 선택 화면이 없는 진입점(similar_only=False)은 어느 행에도 유효 선택이 없을 때만
  종전 후보 규칙(차단 또는 임계치×0.9)을 쓴다. 이 진입점들은 규칙 판정만 하고 선택을 받지 않는다.
- CLI·MCP·Streamlit 활용 제안은 선택 화면·AI 판정이 없어 새 규칙으로 [유사함] 0행이 되므로, 판정·선택이 하나도 없을 때만 종전 후보(차단 또는 임계치×0.9)로 대체하는 처리를 유지한다(2026-11-04 소유자 확인).
- REST 비교표·활용 제안 경로는 과제안처럼 지금 AI 판정을 근거로 쓴다(`_current_alerts` — 진행 중이면 기다린다). 기본 선택이 AI 판정에
  달려 있으므로, 이렇게 해야 판정이 끝났는지에 따라 결과가 달라지지 않는다.
- 차단 게이트는 바꾸지 않는다. `effective_blocking` 은 제안자 선택만 본다. 차단 행을 모두 [관련 없음] 으로 골라야 풀린다. '같다' 행의
  기본 선택은 [유사함] 이므로 미리 고른 값이 차단을 풀지 않는다.
- 선택 기록(`similar_choices.jsonl`, `choice_records`)에는 요청에 실린 선택만 남긴다. 서버의 AI 기본 선택은 기록하지 않는다.
  웹은 전부터 미리 고른 값을 요청의 `similar_choices` 로 보냈다(ADR 0039 의 '다르다' → [관련 없음]). 그래서 웹에서 미리 고른 값과
  직접 누른 값은 기록에서 구분되지 않는다. 종전과 같다.

## 웹
- `default_choices` 에 '같다'·'일부 겹침' → [유사함] 이 더해진다. 화면은 선택이 없는 행에만 채운다(`withDefaults`). 그래서 막대의 건수는
  서버 `similar_count` 와 같다.
- 판정 안내에 한 줄을 더한다: "AI 가 '같다'·'일부 겹침' 으로 본 n건은 [유사함] 으로 미리 골랐습니다 — 바꿀 수 있습니다."
  '다르다' 줄은 그대로다. ② 머리 설명에도 미리 고르는 규칙을 적는다.
- 눌린 선택을 다시 눌러 지우면 그 행의 AI 기본 선택으로 돌아간다. 서버도 선택이 없는 행을 기본 선택으로 세므로, 화면에서 빈칸으로 두면
  막대 건수가 서버와 어긋난다.
- [선택 적용] 전 활용 제안 버튼의 [유사함] 건수는 서버와 같은 기본 선택으로 센다.

## 결과
- 같은 알림이면 네 진입점의 [유사함] 행·'새 영역' 다시 받기 여부·활용 제안 대상이 같다. `tests/application/test_similar_rows_entrypoints.py` 가
  REST·CLI·MCP·Streamlit 에서 이를 비교한다. 유효 선택이 없을 때 선택 화면이 없는 진입점만 종전 후보를 쓰는 차이도 함께 확인한다.
- AI '일부 겹침' 행을 고르지 않았으면 그 행이 [유사함] 이다. 이때 '새 영역' 다시 받기를 하지 않고, 비교표에 그 행이 들어가며,
  `/v1/precheck` stage=full 은 활용 제안을 붙인다.
- 골든셋 03(철도 무관)은 그대로 차단 0·[유사함] 0·기본 선택 없음이다.
- 가짜 모드: 아이디어에 "(추천 없음)" 이 있으면 같음 판정이 모두 '다르다' 다. 그래야 e2e 의 '유사함 0·참고 0' 장면이 유지된다.
- 손대지 않은 것: ③ 특이사항 판정표(`rows_for_writing`)는 요청 선택만 본다. 웹은 미리 고른 값을 함께 보내므로 실제 화면 경로는 같다.
  CLI `rra compare`(similar_only=False)는 상위 알림 그대로다.
