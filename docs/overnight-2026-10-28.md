# 2026-10-28 새벽 작업 기록 — 아침 시범 전 수정 [F1]·[F2] (마감 07:30)

지시(01:4x): [F1] 빈 초안 방지(원인 표·수정·Gemini 대체 작성·실패 섹션 버튼·골든셋 재측정 유효 9/10), [F2] 유사과제 판정은 과제형 자료원만(논문·보고서는 "관련 연구")·precheck 적중 9/10·지연 2초. 마무리: PR 병합 → web 빌드 → api 재시작 → healthz·로그인·생성 1회. Gemini 기타 60회. Tailscale public_origin. 공용 계정 비밀번호 최소 4자(시범 한정). 07:30 못 채우면 안전한 부분만.

## 진행 기록

| 시각 | 내용 | 근거 |
|---|---|---|
| 01:46 | 상태: main 53e5a86(#49), launchd mlx·api 가동(healthz 200), 열린 PR 없음. Tailscale 은 설치돼 있지 않아 `serve status` 주소를 얻을 수 없음 → public_origin 변경 보류(사람 할 일). 레인 배정: [F1] feat/draft-fallback(Gemini ≤45, 마감 06:00, 안전한 4번을 첫 PR), [F2] feat/overlap-sources(Gemini 0~5, 마감 05:30). 통합 담당: 공용 계정 비밀번호 최소 길이 설정화(4자, 시범 한정) | — |
| 01:50 | 공용 계정 비밀번호 최소 길이 설정화 PR #54(auth.yaml guest.min_password_length: 4, 기본 8, 테스트 1,773) — CI 전부 pass 확인 뒤 병합하는 체인 가동. [F1]·[F2] 레인 작업 중 | chain54.log |
| 01:59 | PR #54 병합(CI 7 job 전부 pass 확인 뒤). 레인 [F1]·[F2] 진행 중 | chain54.log |
| 02:14 | [F1] 첫 PR #55 병합(빈 초안 금지: 실패 섹션만 빈칸·목록, 전부 실패일 때만 invalid, ADR 0027). [F2] PR #56(판정 후보 과제형 자료원만, 논문·보고서·특허는 관련 연구) CI 진행 중. [F1] 2차(원인 수정·Gemini 대체·재측정) 작업 중 | gh pr |
| 02:25 | [F2] PR #56 병합: 판정 후보는 과제형 자료원(own·alio·ntis 과제·g2b)만, 논문·보고서·특허는 related_research(웹 ② '관련 연구', 배지 참고). 자료원별 풀 7/28 + reranker 순서 유지. 골든셋 적중 5/10 → **9/10**(03 은 기존 거짓 차단), 지연 1.84~2.09s(중앙값 2.06, 목표 2초를 0.06s 초과 — reranker 단독 지연, 후속). Gemini 0. openapi 재생성 필요(related_research) | 레인 F2 보고, docs/eval-2026-10-28-precheck.md |
| 02:57 | [F1] 1차 재측정(f1_fallback, 브랜치 코드): **유효 10/10**, 점수 평균 2.77, 충족률 0.667, 평균 201s, Gemini 11회. 레인이 2차 확인 측정(f1_fallback2) 3/10 진행 중, PR #57 CI 통과·미병합 | data/eval/f1_fallback.json |
| 03:15 | [F1] 2차 PR #57 병합(02:5x). main 체크아웃 7bb3929(#57)로 당김(처음 `git pull` 이 'multiple branches' 오류 → `merge --ff-only origin/main`), 검사 1,810 통과·계약 8·ruff 0, web 재빌드, api kickstart → healthz 200·무토큰 401·web 200. 생성 1회 확인은 [F1] 2차 측정(f1_fallback2, 8/10) 종료 뒤 자동 실행 | wrapA2.log |
| 03:26 | [F1] 2차 재측정(f1_fallback2, main #57 코드): **유효 10/10**, 점수 평균 2.62, 충족률 0.617, 평균 195s, Gemini 15회 → 두 번 합쳐 빈 초안 0. 생성 1회 확인(최신 main, 골든셋 04): precheck 66.5s → drafted 145s → 최종 검토 15s → HWPX 41,136 bytes, 전체 227s. Gemini 이번 작업 약 30/60 | gen0728.log, data/eval/f1_fallback2.json |
| 03:35 | PR #58([F1] 2차 측정 문서: 유효 10/10·실패 섹션 0·대체 작성 5)·#59(통합 문서) 병합, main 723e336. 열린 PR 없음. 서비스: launchd mlx·api 가동(api 03:15 재시작 = #57 코드, web/dist 03:15), healthz 200. Gemini 이번 작업 약 30/60. 마감 07:30 전 완료 | gh pr, chain59.log |

## 오후 레인 (2026-10-28 13:10~, 지시 [0]~[6] — 판단은 `docs/final-check-2026-10-28.md`)

| 레인 | 작업 | 브랜치 | 상태 | 기다리는 의존 |
|---|---|---|---|---|
| 통합 | [0] 상태 확인·public_origin, [1] 맥 항상 켜짐 | chore/ops-awake-origin | **완료** #68 병합·배포 ab17faa(13:14) | — |
| A | [2] 그림 말로 고치기 = 명세 변경(+ 그림 명세 생성 Argon) | feat/figure-edit-spec | **완료** #70 병합 — 글자 변형 편집 1회당 2~3 → 6회 합계 1, 1회 31~41초 | — |
| B | [3] Argon 먼저 작성·로컬 대체·local_check·동시 생성 | feat/argon-first | **완료** #71 병합(테스트 1,939, e2e 옛 run 시험은 통합 담당이 고침) | — |
| C | [4] 실시간 검색 ScienceON·NTIS·OpenAlex | feat/live-search | **완료** #72 병합(B 위에 rebase, 테스트 +45) | — |
| D | [3]·[4] 화면(로컬 작성·실시간 검색 배지, 자료원별 상태, e2e) | feat/web-argon-live | **완료** #69 병합(문장 origin llm 라벨 "AI 작성", vitest 86·e2e 19) | B·C 병합 뒤 e2e 의 page.route 주입 → 실응답 전환 |
| A2 | 그림 로컬 대체 호출을 로컬 슬롯 안으로 | fix/figure-local-slot | **완료** #73 병합(통합 담당 rebase) | — |
| E | [5] 측정 도구(최종 검토·HWPX·실시간 비율·자료원별·동시 N·비교표) | feat/eval-argon-live | **완료** #75 병합 | — |
| 통합 | [5] 통합 측정·배포, [6] 보고 | — | B·동시 3건 완료(#76·#77 수정 포함) → 배포 진행 → C(18:07 예약) | — |

## 시범 오류·개선 17건 레인 (2026-10-28 16:1x~, 판단은 `docs/final-check-2026-10-28.md` "시범 오류·개선 17건")

| 레인 | 작업 | 브랜치 | 상태 | 기다리는 의존 |
|---|---|---|---|---|
| A | ② 유사과제 흐름 5·6·7·8 | feat/precheck-flow | **완료** #83 병합 — 상위 5 적중 10/10·거짓 차단 0/3·유사하지 않음 2/2, AI 판정 중앙 10.7초, Gemini 39/80, 통합 담당이 #81·#82 와 충돌 해결 | — |
| B | 작성·편집 AI 1·9·13·14·15 | feat/edit-ai | **완료** #84 병합 — 다시 쓰기 0후보 원인 수정, 실호출 2 run × 12섹션, Gemini 49/100, decide_evidence 500 수정 | — |
| C | 그림 3·4·10·11 (As-Is/To-Be·디자인 개선·기본 그림 정리·분석 기법 추천) | feat/figures-v2 | **완료** #81 병합(18:0x) — 백엔드 2058·vitest 95·e2e 18, 그림 15/30·텍스트 3/80, 샘플 docs/history/screens/2026-10-28-figures-v2-* | 캡션 12pt 는 D |
| D | HWPX 서식·화면 편의 12·2·16·17 | feat/format-ui | **완료** #82 병합 — HWPX 서식 골든 10/10·시범 run 19/19, 백엔드 2109·vitest 106·e2e 18, 알림 코드 한국어 설명 빠짐 1건은 통합 담당이 보충 | — |
| 통합 | 합치기·e2e 전체 경로·골든셋 측정·배포·안내서 | — | **완료** #85·#86, 측정 `docs/eval-2026-10-28-pilot-fixes.md`, 배포 d9b2869(20:14) | — |


## 시범 의견 반영 2차 레인 (2026-10-28 21:3x~, 판단은 `docs/final-check-2026-10-28.md` "시범 의견 반영 2차")

| 레인 | 작업 | 브랜치 | 상태 | 기다리는 의존 |
|---|---|---|---|---|
| 통합 | 응답 대기 공용 부품(시간 제한 없음·[취소]) | chore/ai-wait-cancel | **완료** #88 병합 | — |
| A | ② 19·20 + [0] ② 흐름(표 먼저·과제안 미리·더 만들기) | feat/precheck-v3 | 진행 중 | #88 |
| B | 18 정책 근거 재분류·내부 번호 공용 부품·L2 로컬 2차 검토 | feat/policy-l2 | 진행 중 | #88 |
| C | 23 그림 가로 비율·본문 폭 맞춤·글자 크기 | feat/figures-wide | 진행 중 | #88 |
| D | 21 상태 표시 버전 없음·22 아래 이동 막대·25 "run" 표기 | feat/versions-nav | 진행 중 | #88 |
| 통합 | 합치기·e2e·골든셋 측정(실시간 검색 켬·새 점수 규칙)·배포·안내서 | chore/integrate-pilot2 | 준비(골든셋 정답 2건·Argon 응답 시간 기록) | 네 레인 |
