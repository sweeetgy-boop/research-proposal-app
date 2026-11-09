# 현황 조각 — feat/wave-b-branch-switch-policy-quote (레인 B, 2026-11-09)

| 항목 | 상태 | 비고 |
|---|---|---|
| (3) novel ↔ 차별화 전환 | 완료(웹) · 서버 안전망은 통합 연결 대기 | (a)(b) 모두 [선택 적용] 한 번 — 가짜 모드 e2e 2건. 차단 행만 바꾼 틈은 `planKey` 로 닫음. `recommend_switch.py` + `RecommendationApplyIn.request`; app.py 더/적용 핸들러 연결은 PR 설명 조립 변경 절 |
| (4c) 정책 근거 인용 잘림 | 완료 | `normalize_pdf`·`widen_to_sentences`·`is_fragment`·`Passage.complete`, ①②(추천·작성안) 공용 `policy_passage`. 운영 DB 측정은 건수만(각주형 2,054/22,643) |
| 알림 코드 | `mode_changed` | `problem_labels.py` = `labels.ts` |
| 검사 | pytest 2675 passed/21 skipped · lint-imports 8 kept · ruff 0 · vitest 270 · e2e 53(새 2건 포함, 전체 돌림에서 `argon-live` 1건이 ② 진입 10초 시간 초과로 한 번 실패 — 내 변경 전 단계, 단독 3회 재실행 통과) | 기준선 2665 / 264 / 51 |

납품: `src/rra/entrypoints/api/recommend_switch.py`, `src/rra/domain/rules/policy_phrases.py`, `web/src/features/precheck/model.ts`,
`web/src/routes/Precheck.tsx`, `web/e2e/branch-switch.spec.ts`, `tests/fixtures/policy/footnote_passage.txt`, ADR 0061.
