# feat/precheck-v3 — ② 유사과제 확인 v3 (레인 A, 2026-10-28 밤, ADR 0039)

## 현황 행 (docs/status.md 에 옮길 것)
| 항목 | 상태 | 비고 |
|---|---|---|
| [0] ② 흐름: 표 먼저·과제안 미리·응답 대기 | 완료 | `POST /v1/precheck?stage=rule` → `/judgment`·`/recommendations` 동시(서버가 같은 판정 작업 공유, 과제안은 AI 판정을 기다려 근거로), 판정·다듬기·원문 추출 제한 시간 제거, ② AI 경로 전부 `cancel_on_disconnect`, 화면 "경과 n초 [취소]" |
| 20 선택 적용과 표 정리 | 완료 | 선택 요약 막대(`SummaryBar`, `bottom: var(--stepnav-h)`) [선택 적용]·[차별화 과제안 더 만들기], 판정 칸 매핑, 관련도 높음/보통/낮음(유사도 숨김), 일반어 37개, "다르다" 만 기본 [관련 없음] |
| 19 차별화 과제안 카드 | 완료 | 근거 제목·자료원 상위 3 + [더 보기], 카드 겹침 재판정(② 같은 기준 → 같다면 그 카드만 한 번 다시 → 남으면 제목·겹치는 점), 차별성 순 정렬, `/recommendations/more` |

## 산출물
- 백엔드: `domain/rules/{precheck_levels,card_overlap}.py`, `usecases/card_overlap.py`, `precheck_overlap`(rule_stage remember·judgment·current·공유 작업), `recommend_projects`(card_check·shown·refs·정렬),
  `judge_sameness`·`polish_field`·`extract_cells` 제한 시간 제거, REST `stage=rule`·`/judgment?retry`·`/recommendations/more`, `views` 판정 칸·관련도·자료원·카드 refs/겹침 칸,
  `config/overlap.yaml`(judgment.cards, 제한 시간 키 삭제, 일반어 37), 가짜 모드 답(겹침 확인·더 만들기·다시 받기), `tools/eval_precheck_v3.py`.
- 웹: `features/precheck/{SummaryBar(새),SimilarRowsTable,PlanCards,JudgmentNotice,PlanEditor,model}`, `routes/Precheck.tsx`(표 먼저 오케스트레이션), `routes/Idea.tsx`(precheckFast),
  `api/{endpoints-precheck,types-precheck}.ts`, `features/idea/store.ts`(appliedChoices), `features/idea/{RelatedResearchList,AlertsTable,NtisInsights}.tsx`(내부 번호·유사도 숨김).
- 테스트: 백엔드 +15(유스케이스 12·REST 2·설정 1), vitest +7(`PrecheckV3.test.tsx`), e2e `precheck-v3.spec.ts` + 기존 4개 spec 을 [선택 적용]·새 표시에 맞춤.

## 판단
| 판단 | 이유 |
|---|---|
| 응답 나누기는 경로 두 개(stage=rule → /judgment)로, SSE 는 쓰지 않음 | 판정 전용 경로가 이미 있음([다시 시도]). 두 요청이면 취소도 요청 단위로 깔끔 |
| 과제안은 표가 보이자마자 요청하되 서버가 AI 판정을 기다려 근거로 씀 | AI "다르다" 행을 빼야 엉뚱한 과제안이 안 나온다(ADR 0036 배경). 판정은 한 작업을 공유해 두 번 부르지 않는다 |
| 기다리는 요청이 모두 끊겨야 판정 작업 취소 | 판정 [취소] 를 눌러도 과제안이 판정을 기다리고 있으면 계속(과제안은 그 판정을 쓴다). 화면은 규칙 기준 그대로 |
| 관련도 높음 ≥ 0.8 · 보통 ≥ 0.5 · 낮음 | 0.5 = 규칙 차단 하한(v2 측정), 0.8 = 정답 9건 중 8건이 넘은 값 |
| 기본 [관련 없음] 은 AI "다르다" 만 | 지시서. 기본 선택도 [선택 적용] 전까지는 비교표에 반영되지 않는다("선택이 바뀌었습니다" 안내) |
| 선택 요약 막대는 화면 끝에 sticky(bottom: --stepnav-h) | 화면 끝에 두어야 스크롤 내내 보인다(표 바로 아래에 두면 지나간 뒤 사라짐) |
| 카드 겹침 기준 = 카드 글 규칙 판정(아이디어 핵심어) + Argon 한 번 | 지시서 "item 5 와 같은 기준". 카드마다 호출하지 않고 한 번에 — 호출 수 |
| 카드 글에서 차별점 문장은 뺌 | "기존 과제는 …" 문장이 기존 과제를 말해 그 과제와 가깝게 나온다 |
| AI 확인 실패면 규칙 기준 경고만, 다시 받지 않음 | 다시 받기는 AI "같다" 일 때만(지시서), 실패는 사유를 보인다 |
| 더 만들기 카드는 뒤에 붙임(전체 재정렬 안 함) | 앞 카드의 번호·선택을 바꾸지 않으려고. 각 묶음 안에서는 차별성 순 |
| 과제안 상한 15(한 번 5) | 세션 메모리·화면 길이. apply index 상한 4 → 14 |
| 일반어 37개 | 시범 실시간 검색 Argon 키워드 30건 + 시범 run 알림 키워드에서 분야 가리지 않고 나온 낱말. 분야 고유어·붙여 쓴 복합어(수송수요·차량기지)는 두지 않음 |
| 실시간 검색 키워드의 6초 제한은 그대로 | 표 먼저의 대기 시간이라 AI 버튼 응답이 아니다 — 넘으면 규칙 키워드(사유 표시는 기존) |
| 측정 API 포트 8041 | 8021 은 launchd 가 잡고 있어 열 수 없었다 |

## 프론트엔드 영향 (통합·레인 D)
- `POST /v1/precheck?stage=rule` 응답 `judgment.status = "pending"`, `default_choices[]`; 알림 행 새 칸 `level·level_label·level_basis·level_basis_label·relevance·relevance_label·source_label`.
- `POST /v1/precheck/judgment?retry=true|false`, `POST /v1/precheck/recommendations/more {request, rec_id}` → `recommendations.{added, added_reason}`.
- 카드 새 칸 `refs[{doc_id,title,source_label}]·overlap_titles·overlap_reason·overlap_by(_label)·regenerated·difference(_label)·added`, 묶음 `overlap_checked·overlap_found·overlap_regenerated`.
- openapi.json·schema.d.ts 재생성 필요(통합 담당). `RecommendationApplyIn.index` 상한 14.
- 선택 요약 막대는 ② 화면 끝 sticky, `bottom: var(--stepnav-h, 0px)` — 레인 D 막대 높이 변수만 쓴다.
