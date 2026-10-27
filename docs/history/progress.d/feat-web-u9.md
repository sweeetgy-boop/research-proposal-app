# feat/web-u9 진행 메모 (웹 레인 U9)

- 2026-10-27 시작. main 32dcaf0(PR #27 병합) 기준 worktree `rra-wt/feat-web-u9`. `rra api schema` → openapi.json 41 경로,
  `npm run gen:api` 로 schema.d.ts 재생성(커밋 1).
- 계획: api(endpoints·types·hooks) → ① 간편 입력(StructureForm)·정책 근거 추천(probe) → ② 비교표 → /new/brief → 초안 근거 패널 →
  편집 다시 쓰기·보완 질문 → /runs/:id/submit-check(usage·만족도) → stepper → 단위 테스트·e2e → 측정·문서.
- 가짜 백엔드 확인 사항: ScriptedComposeLLM 은 [섹션: key] 만 알아 structure(JSON 객체 기대)·brief 는 parse_failed 가 된다 →
  adapters/fake/llm.py 에 두 프롬프트 분기 추가 예정(e2e 가 간편 입력·브리핑 경로를 지나도록).
- 가짜 백엔드로 신규 13 경로 응답 모양 확인(curl) → types.ts·fixtures. 초안 응답에 sentence_id 없음 → `s:<key>:<i>` 로 생성.
  fake llm.py 분기 커밋(59dda4e), 백엔드 entrypoints 161 통과·lint-imports 8 kept.
- 화면 8종·단위 테스트 7 파일(dcf6e52). 정책 근거 추천을 화면 로드 때 probe 하면 405 콘솔 오류로 CSP e2e 가 깨져 버튼 호출로 바꿈(487ecce).
  e2e 10 통과(기존 8 은 브리핑 경유·상세 입력 전환 반영). 캡처 8장·녹화 webm.
- origin/main(PR #28 이미지 판독) 병합 — 충돌 없음, openapi/schema 재생성(변화 없음), 백엔드 779·e2e 9+1skip·lint·typecheck 통과.
  Lighthouse /login 100/100/100; 로그인 뒤 화면은 쿠키 헤더만으로는 안 됨(sessionStorage CSRF 게이트) — README 에 기록. 문서 조각 작성.
