# 레인 B 진행 기록 — feat/edit-ai (2026-10-28, 작성·편집 AI 기능)

## 경과
- 2026-10-28 17:10 탐색. 시범 runs 의 `rewrites/rewrite_*.json` 4건이 모두 `policy_importance`·후보 0문장·dropped 0
  (두 사용자, 정책 근거 빈 run). 같은 run 의 다른 섹션 다시 쓰기는 v3·v5·v6 으로 반영되어 있었다.
  가짜 LLM·복사한 실 run 으로 12개 섹션을 돌려 재현: `policy_importance`(입력 전용 + policy_basis 없음)는
  LLM 을 부르지 않고 빈 후보를 조용히 돌려준다(사유 없음) → 화면 "후보 0문장". `overlap_review` 는 409.
  Argon 실호출 3섹션×2 run(6회) 은 후보 1~8문장 — 원격 작성 경로 자체는 정상.
- 2026-10-28 17:20 API 오류 로그에서 별도 결함 발견: `decide_evidence` 가 `sorted(dict…)` 로 TypeError(500) —
  이미 판단이 있는 문장에 근거 승인을 다시 누르면 실패. 고침(값 묶음 비교).
- 2026-10-28 18:30 백엔드: Argon 먼저 공용 호출(`usecases/argon_first`), 정책적 중요도 작성안
  (`domain/rules/policy_cards`·`usecases/policy_cards`), 보강 질문 개편(`clarify_input.inspect`, 켬),
  보완 질문(`usecases/section_questions`, 모든 섹션 체크리스트), 다시 쓰기 사유·새로 쓰기·rewrite_llm,
  변경 세기(`domain/rules/change_count`), REST 6 경로(`entrypoints/api/edit_ai_routes.py`). 전체 2021+ 통과.
- 2026-10-28 19:20 [일시 정지 — 기계 이동] 백엔드 완료·테스트 2045 통과·ruff·format·lint-imports(PYTHONPATH=src) 통과.
  가짜 모드 새 필드 포함(정책 자료 3건 시드, 보강 질문·작성안·다듬기·보완 질문 응답). Gemini 실호출 6/100.
  웹: `api/types-editai.ts`(types.ts 에서 re-export)·`api/editai.ts`·`features/policy/model.ts` 까지(미검증, npm ci 완료).
  다음: `features/policy/PolicyCards.tsx`(카드·합치기·직접 수정+AI로 다듬기·직접 작성·없음) → Clarify.tsx 개편(상태별
  사유·다시 시도·정책 카드, RunIn.policy_choice) → SectionRewrite(문구 "Argon 이 같은 지시·근거로 다시 씁니다", 사유·
  다시 시도·새로 쓰기·정책 카드 연결) → SectionQuestions(source 배지·[답 반영해 다시 쓰기]) → Edit.tsx(변경 n건 =
  서버 /changes + 로컬, 버튼 항상 켬, 변경 없음/있음 팝업 → 최종 검토) → vitest·axe·e2e → 실호출 확인(2 run×12섹션) →
  ADR·status/timeline/metrics 조각 → PR. 반쯤 된 단계 없음(커밋 b33d34e 기준 깨끗).
- 2026-10-28 (재개) 웹 완료 — `features/policy/{PolicyCards,RunPolicyDialog,model,store}`, Clarify.tsx 개편, SectionRewrite·
  SectionQuestions 새 필드, `features/versions/SaveVersionFlow`, Edit.tsx 저장 흐름. vitest 112·axe 0·e2e 20(새 edit-ai 2).
  origin/main(그림 v2 #81) 위로 한 커밋으로 rebase — 충돌 submit_check 독스트링·types.ts re-export 만. 변경 세기에 추천 그림
  결정(accept·dismiss·restore·swap) 추가. 백엔드 2084 통과. ADR 0037·조각 작성. 실호출 확인(2 run × 12섹션) 진행.
