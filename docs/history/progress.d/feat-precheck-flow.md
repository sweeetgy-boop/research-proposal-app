# feat/precheck-flow 진행 기록 (레인 A — ② 유사과제 흐름)

- 17:10 시작. 골든셋 10 + "유사하지 않음" 2건(`tests/golden/not_similar/`) 측정 스크립트로 후보 풀·reranker 점수·핵심 키워드 원자료 수집
  (Gemini 12회 — 키워드). reranker 점수가 0~1 로 뚜렷이 갈림(무관 0.00~0.07, 같은 과제 0.87~0.99), e5 는 0.83~0.90 에 몰림.
- 17:20 AI 같음 판정 1차(Gemini 12회): 같은 과제만 same, 시범 거짓 차단 과제는 상위 10 밖·different. 07 은 60초 시간 초과 → 규칙 대체.
  규칙 판정 임계: reranker 0.5 + 핵심 키워드 1개 → 차단 적중 9/9, 거짓 차단(유사하지 않음·03) 0/3 (종전 e5 규칙 1/3).
- 17:40 도메인·유스케이스: reranker 점수 중심 규칙, 같은 제목 합치기, SameJudge(Argon → 로컬 → 규칙), [유사함]/[관련 없음] 선택 규칙·기록,
  비교표 원문 추출(CellExtractor), 과제안 칸(goal·method·scope)·추천 완화·한 번 다시 받기, [AI로 다듬기].
- 18:10 REST: `/v1/precheck` 응답 확장(judgment·choice·gate_reason), `/precheck/judgment`·`/choices`·`/plan/polish`, `GET /runs/{id}/comparison`,
  RunIn `similar_choices`·`method`·`scope`·`idea_versions`. 가짜 LLM 답(`adapters/fake/precheck.py`).
- 18:30 **일시 중지(장비 이동)** — WIP 커밋·푸시. 상태:
  - 백엔드 전체 테스트는 직전 커밋 기준 통과. 새 `tests/entrypoints/test_precheck_flow_api.py`(가짜 모드 ② 전체 경로) 는 마지막 단언 하나
    (선택 기록의 `released` 값, 162행 근처)에서 실패 중 — 기록 쪽 released 계산 확인 필요(나머지 단언은 통과).
  - 측정 원자료·스크립트는 작업 세션 임시 폴더(scratchpad/meas) — 저장소에 없음. Gemini 사용 24/80.
- 다음: (1) 위 테스트 수정 + 도메인 단위 테스트(같은 제목 합치기·선택·같음 판정·비교표 칸·다듬기 검증) (2) 웹: `web/src/features/precheck/`
  새 컴포넌트(행별 선택·AI 판정 안내·[다시 시도], 비교표 최소 폭/카드, 과제안 카드+수정 폼+[AI로 다듬기], 다음 버튼 사유), `api/types-precheck.ts`,
  vitest·axe·e2e 1개 (3) 최종 측정(AI 판정 포함 hit·거짓 차단·지연) → `docs/eval-2026-10-28-precheck-v2.md` (4) status·timeline·metrics 조각·ADR·PR.
