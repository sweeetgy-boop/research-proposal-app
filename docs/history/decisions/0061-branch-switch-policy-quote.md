# ADR 0061 — ② 과제안 갈래 전환은 버튼 한 번(선택 적용)으로, 정책 근거 인용은 문장 경계·각주 제거 (2026-11-09, feat/wave-b-branch-switch-policy-quote)

## 맥락
- ADR 0057 로 ② 과제안이 두 갈래(novel / 차별화)가 되었다. novel 세션의 `/recommendations/more`·`/{id}/apply` 는 409
  ("새 과제안은 [과제안 다시 만들기]로 …")다. 제안자가 행의 [유사함]/[관련 없음] 을 바꾸면 갈래가 달라지는데, 이때 409 가
  전환을 막는지 확인해야 했다.
- 확인 결과(가짜 모드 e2e): [선택 적용] 은 `/precheck/recommendations` 를 새로 부르므로 409 를 거치지 않고 새 갈래 카드가
  보인다 — (a) novel→차별화, (b) 차별화→novel 모두. 다만 틈이 하나 있었다. 과제안을 다시 받을지 정하는 서명
  (`planSignature`)이 [유사함] 집합만 보므로, **차단 행(판정 없음)만 [관련 없음] 으로 바꾸면** 유사함 집합은 그대로("")인데
  갈래는 차별화→novel 로 바뀌어 과제안을 다시 받지 않았다. 또 서버는 세션 갈래와 지금 선택의 갈래가 달라도 더/적용을 그대로
  이어 갔다(novel 세션이면 "새 과제안은 …" 409 — 사용자에게는 뜬금없다).
- 정책 근거 1순위 인용(ADR 0052 팝업·작성안)이 PDF 추출 문장 중간에서 잘렸다 — 운영 사례 "…하자보수73)하였으나 …"(각주 73 이
  단어에 붙고 문장 앞이 없음). 운영 DB 정책 자료원 청크 22,643건 가운데 각주형 패턴 2,054건, 조사로 시작 539건, 문장 끝 없음
  18,507건(건수만 확인, 본문 인용 없음).

## 선택지
1. 그대로 둔다 — 전환은 되지만 차단 행만 바꾼 경우와 서버 409 문구가 남는다. 인용은 청크 안에서만 고른다.
2. **웹 서명에 갈래를 넣고(planKey = 갈래 + 유사함 서명) 더/적용 전에 갈래를 먼저 비교**하며, 서버는 세션 갈래와 지금 갈래가
   다르면 `mode_changed` 문제 응답(안전망). 인용은 문서 본문에서 문장 경계까지 넓히고 각주·하이픈을 걸러 내며 불완전하면 뒤로.
3. 서버만 고친다(409 → mode_changed) — 웹이 응답을 받아 다시 받는 왕복이 늘고, 차단 행만 바꾼 틈은 남는다.

## 결정
2를 택한다. 핵심은 웹이고 서버 변경은 최소다.
- **웹** `features/precheck/model`: `expectedMode`(서버 `similar_rows.recommend_mode` 와 같은 규칙 — [유사함] 0건(선택 없는
  행은 AI 기본 선택) AND 차단 없음(제안자 선택만) → novel), `planKey`(갈래:유사함 서명), `modeMismatch`, `isModeChanged`.
  `Precheck.tsx` 는 planSig 에 planKey 를 저장하고 [선택 적용] 때 planKey 가 다르면 과제안을 다시 받는다. [더 만들기]·카드
  적용은 먼저 `modeMismatch` 를 보고 다르면 `/more`·`/apply` 대신 과제안을 새로 받으며("선택이 바뀌어 과제안을 다시 받습니다"
  토스트), 서버 409 `code=mode_changed` 를 받아도 같은 길로 간다. 되돌림(`novelty_reverted`) 과제안과 갈래를 모르는 옛 응답은
  전환으로 보지 않는다(되풀이 방지).
- **서버** 새 모듈 `entrypoints/api/recommend_switch.py`(순수 헬퍼): `mode_changed`·`check_mode_unchanged`(→ `ModeChanged`)·
  `mode_changed_response`(problem+json 409 + `code`). `RecommendationApplyIn.request`(선택)로 적용 때도 지금 선택을 받을 수
  있다. **app.py 는 공용 파일이라 고치지 않았다** — 더/적용 핸들러·예외 처리기 연결은 PR 설명 "통합 때 메인이 반영할 조립 변경".
  코드 `mode_changed` 는 `problem_labels` 두 표에 함께 넣었다. 웹 `Problem.code`(선택).
- **인용** `domain/rules/policy_phrases`: `normalize_pdf`(단어 끝 1~3자리 숫자+`)` 각주 — 앞 글자가 '제' 이거나 4자리(연도)·
  줄 머리 번호는 제외, 위첨자 숫자, 줄 끝 하이픈), `widen_to_sentences`(청크를 `doc.body` 에서 찾아 앞은 직전 문장 경계·뒤는
  다음 문장 끝까지, 각 400자 안), `is_fragment`(조사·어미·영문 소문자로 시작, 문장 끝 없음, 12자 미만), `pick_passage` →
  `Passage(quote, hits, complete)`: 고르는 순서 = 키워드 겹침 있음 > 온전함 > 겹침 수 > 앞 문장. `policy_passage`(①②
  공용 규칙)는 Passage 를 돌려주고, `PolicySuggestion.complete`·`rank()`·`PolicyCards.passages` 가 불완전한 인용을 뒤로 보낸다
  (폐기 아님). `match_text` 도 각주를 지워 생성 때 원문 대조(보안 A)가 넓힌 인용을 찾는다. 글자 자체는 고치지 않는다.
  fixture `tests/fixtures/policy/footnote_passage.txt` 는 운영 조각을 넣어 지어낸 문단이다(실제 PDF 원문 아님).

## 결과
- e2e `web/e2e/branch-switch.spec.ts` 2건((a) novel→차별화, (b) 차단 해제→novel), vitest `branchSwitch.test.ts` 10건,
  pytest `test_recommend_switch.py`·`test_policy_quote_boundaries.py`.
- 화면 문구에 코드·내부 번호·"run" 이 나가지 않는다(e2e `expectNoInternalIds`).
- 남은 것: app.py 연결(통합), `docs/openapi.json` 재생성(`RecommendationApplyIn.request`), 운영 정책 문서로 1순위 인용 길이·
  온전함 비율 측정(건수만).
