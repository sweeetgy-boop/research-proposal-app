# feat/precheck-flow — ② 유사과제 흐름 (레인 A, 2026-10-28)

## 현황 행 (docs/status.md 에 옮길 것)
| 항목 | 상태 | 비고 |
|---|---|---|
| 5 판정 정확도·사용자 선택 | 완료 | reranker 0.5 + 핵심 키워드 1 규칙, 일반어 40여 개 추가, 같은 제목 합치기, 상위 10 Argon 같음 판정(→로컬→규칙, [다시 시도]), 행별 [유사함]/[관련 없음], 차단 해제, 선택 기록 JSONL, 골든셋 유사하지 않음 2건. 측정 docs/eval-2026-10-28-precheck-v2.md, ADR 0036 |
| 6 차별성 비교표 | 완료 | [유사함] 행만, 없으면 안내. 제안 행 가제·연구방법 입력 수정, 초안 뒤 `GET /v1/runs/{id}/comparison`. 기존 과제 칸 Argon 원문 추출(원문 대조), 적용범위 없으면 "정보 없음". 표 최소 폭·가로 스크롤, 좁은 화면 카드 |
| 7 차별화 과제안 고르기·직접 고치기 | 완료 | 카드 다섯 칸 + 근거, [이 안으로 진행]·[원래 아이디어 유지]·[직접 작성](칸별 [AI로 다듬기]), 원래와 비교, `idea_versions.json`, 선택 바뀌면 [과제안 다시 만들기] |
| 8 활용 제안·과제 추천 오류 | 완료 | 활용 제안은 [유사함] 행만(없으면 안내 + 과제안이 방향 제안), 추천 검증 완화(부가 칸만 비움·범위 밖 id 만 뺌)·제외 사유 표시·2건 미만이면 사유 주고 1회 재생성, 다음 버튼 막힘 사유 |

## 산출물
- 백엔드: `domain/rules/{same_judgment,similar_choice,idea_plan,precheck_view}.py`, `domain/models/idea_plan.py`, `usecases/{judge_sameness,extract_cells,polish_field}.py`,
  `ports/choice_log.py`·`adapters/logging/choice_log.py`, `adapters/fake/precheck.py`, overlap·keywords·comparison·recommendation·differentiation·precheck_overlap·
  compare_projects·recommend_projects·differentiate·generate_proposal(선택 반영) 수정, REST `/v1/precheck/judgment`·`/choices`·`/plan/polish`·`GET /v1/runs/{id}/comparison`.
- 웹: `web/src/features/precheck/*`(SimilarRowsTable·JudgmentNotice·ComparisonView·PlanCards·PlanEditor·NextGate·model), `api/types-precheck.ts`·`api/endpoints-precheck.ts`,
  `routes/Precheck.tsx` 재구성. 옛 `features/idea/{RecommendationCards,ComparisonTable}.tsx` 제거(PlanCards·ComparisonView 로 합침).
- 테스트: 백엔드 테스트 함수 +30·개정 2(규칙 12·유스케이스 7·REST 흐름 1·설정 3·추천 7), 웹 vitest +7(axe 0, 옛 비교표 테스트 2 제거), e2e `precheck-flow.spec.ts` 1 + u9 개정.

## 판단 기록
- AI 판정은 같다만 차단 — 골든셋 정답("관련 선행 과제")의 다수는 "일부 겹침" 으로 근접 표시. 차단을 넓히지 않고 제안자 선택으로 넘긴다.
- 처음 ② 진입 때 행은 아무것도 고르지 않은 상태(AI "같다" 도 미리 고르지 않음) — 비교표는 "유사한 과제를 고르면…" 으로 시작.
- 차단 해제 판단은 같은 입력 글(가제·현황·원인·한계·목표)의 판정 메모 기준. 과제안 카드로 가제·목표가 바뀌면 생성 게이트는 새 글로 규칙 판정을 다시 한다.
- `idea_versions` 는 화면이 입력(request) 안에 실어 보낸다 — Clarify(③)의 RunIn 펼침이 그대로 싣는다. 다른 경로(ProposalRequest)는 모르는 칸이라 무시.
- 판정 결과는 입력 글 해시로 30분 메모(프로세스 메모리). 추천의 자기 중복 검사 등 내부 호출은 메모가 없으면 규칙만(외부 LLM 추가 호출 없음).
- precheck 자동 차별화 제안(차단일 때)은 없앴다 — [유사함] 을 고른 뒤에만. 과제 추천 자동 1회는 유지하고 AI 판정과 동시에 돌린다.
- 로컬 대체 모델: 판정·원문 추출·다듬기 = `judgment.local_stage`(clarify), 추천·활용 제안 = compose. 로컬 호출은 생성과 같은 슬롯 안.
- 판정 제한 시간 40초(측정 최대 40.1·60초 초과 각 1건).
- 일반어 후보 파일(`config/generic_terms.candidates.yaml`, 원 저장소)에는 2건뿐 — "응용연구" 만 옮기고 "궤도"(철도 용어)는 두지 않았다.

## 프론트엔드 영향 (레인 D)
- 새 API: `GET /v1/runs/{id}/comparison` — run 화면에서 초안 기준 비교표가 필요하면 `api/endpoints-precheck.runComparison` + `features/precheck/ComparisonView` 를 그대로 쓸 수 있다(이번 PR 은 run 화면을 건드리지 않음).
