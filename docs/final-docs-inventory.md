# 문서 목록과 분류 (2026-10-29, docs/final-docs → 오후 2차 docs/final-docs-2)

저장소의 md 파일 257개(이 파일 포함). 분류: **최신**(지금 사실과 맞음 — 날짜 붙은 기록은 그 시점 기록으로 정확),
**고침**(이번에 고침), **낡음(보관)**(이전 방식·지난 계획 — 지우지 않고 머리에 "보관" 표시, 지금 사실은 표시한 파일에서 본다).
집계(1차, 오전): 고침 28 · 낡음(보관) 12 · 최신 217. 오후 2차는 아래 §0.
UI 레인(Research Studio, 배포됨 c277253 2026-10-29 10:48) 조각 `docs/status.d/feat-ui-studio-{frame,home,search,tokens}.md` 은 pilot-guide·web/README·status·timeline·metrics·보고서 재료·ADR 0048~0051 에 모았다(레인 4 의 ①~⑥ 안쪽 화면은 tokens 조각에 함께 있다).

## 0. 2차 최신화 (2026-10-29 오후, docs/final-docs-2)

1차(오전, #103) 뒤 바뀐 사실: 3차 골든셋 전체 측정 안 함(#109), ① 정책 근거 추천 팝업·③④⑥ 다시 넣는 길(#110, ADR 0052),
16:06 배포 36e0709 + 기록 고침(#111). md 는 259개(1차 257 + ADR 0052 + 배포 기록 16:06). 방법: 모든 md 에서 낡은 표현(운영 버전 c277253,
시험 수 2,418·vitest 201·e2e 40, [추천 받기]·[정책 근거 고르기], "선택 입력 (가제·정책 근거…", 골든셋 "밤 예정", ADR 0051 까지, 경로 70)을 찾아
**살아 있는 문서는 지금 사실로 고치고**, 날짜 붙은 기록(연표 조각·배포 기록·측정 보고서·레인 조각·ADR 본문)은 그대로 두고 바뀐 곳에만
"이후 변경"/"상태" 한 줄을 달았다. 프롬프트 md 25개(`src/rra/adapters/llm/prompts/`)는 모델 동작을 바꾸는 코드라 손대지 않았다.
집계(2차): 고침 23(+ 화면 글 `web/src/features/guide/content.tsx`) · 나머지 236 은 1차 분류 그대로(새 파일 2개는 최신).

| 사실 | 달랐던 곳 | 맞춘 값(근거) |
|---|---|---|
| 운영 버전 | README·status·pilot-guide·architecture·보고서 재료·발표 자료·web/README: c277253(10:48) | 36e0709(2026-10-29 16:06, #110) — 화면 Research Studio 는 c277253 부터(`docs/history/deploys/2026-10-29-1606.md`) |
| 시험 수 | README·summary·web/README·보고서 재료 ⑧: pytest 2,418 · vitest 201 · e2e 40 | pytest 2,419 · vitest 214 · e2e 43(+3 skip) · 계약 8(#110) |
| ① 정책 근거 | demo-script·web/README·architecture·ADR 0040: [추천 받기]·[정책 근거에 추가], "버튼을 눌렀을 때만" | 네 칸이 채워지면 팝업 자동, 1순위 미리 체크·[적용] 해야 들어감·[나중에 넣기](ADR 0052) — 옛 설명은 "이전 방식" 표시 |
| ④ 정책 근거 단추 | ADR 0037·e2e 설명: [정책 근거 고르기] | [정책 근거 넣기·바꾸기](늘 보임·빈칸 안내 줄·직접 입력) |
| 3차 골든셋 | 보고서 재료 ⑩ "밤 예정", ⑧ "재측정은 대기" | 하지 않기로 함(10-29 소유자, #109) |
| 배포 횟수 | 보고서 재료 ⑨ 11회, summary 10회 | 12회(10-28 8회 + 10-29 02:07·09:30·10:48·16:06) |
| 작성 가이드 소요 시간 | 화면 글 "생성 약 3~4분(이 중 그림 약 2분)" | 초안 글 약 1분 30초 먼저, 그림까지 약 3분(배포 확인 각 1건) — pilot-guide §3 와 같게 |
| 배포 기록 반영 PR | 16:06 기록 "#103" 만 | #110(기능)·#103·#109(문서). 원인: 도구가 병합 커밋에서만 번호를 모음(squash 는 빠짐) — deploys/README·lessons·status |
| REST 요약 | deploy/README §4: 10-26 무렵 경로만 | 주요 경로 묶음 + "전체 71 경로" (`docs/openapi.json`) |
| 판단 기록 10-29 | B 병합 #98·09:30·10:48 배포 행 없음 | 행 보탬, 오후 4차 의견·16:06 배포·문서 2차 행 추가(정확한 시각을 모르는 행은 "오후") |

| 파일 | 2차 분류 | 바꾼 것 |
|---|---|---|
| `README.md` | 고침 | 현재 상태: 운영 36e0709, 흐름에 ① 팝업·④ 단추, 시험 수·REST 71·ADR 0052, 측정 결정 |
| `CLAUDE.md` | 고침 | 정책 근거 팝업 줄에 배포 버전 |
| `deploy/README.md` | 고침 | 인증(세션 종류), REST 요약에 10-27~29 경로 묶음 |
| `web/README.md` | 고침 | 정책 근거 팝업·다시 넣는 길 단락(파일·함수), 파일 지도(PolicyPickDialog·features/policy), 시험 수, U9 메모 이전 방식 표시 |
| `docs/architecture.md` | 고침 | 머리 메모(정책 근거·운영 버전 확인법), §4.24 ADR 0052, §4.25 정책 근거·화면·배포 행, §10 10-28·10-29 오전·오후 행 |
| `docs/status.md` | 고침 | §0 16:10 기준·운영 버전·정책 근거 행, §3.2 팝업 의견·배포 기록 병합 방식, §6 #109·#110·문서 2차 행 |
| `docs/pilot-guide.md` | 고침 | §1 16:06 배포 안내, §3 지금 소요 시간·10:48 배포 확인값·인용 잘림 안내(§2 는 #110 에서 고침) |
| `docs/final-report-materials.md` | 고침 | 머리·① 운영 버전, ② 10-29 오후 3행, ③ 데이터 흐름 ① 정책 근거, ④ ①·③·④·⑥·공통 행, ⑥ 정책적 중요도, ⑧ 생성 시간·정책 빈칸(시범 6/7)·시험 수·접근성, ⑨ 배포 12회·4차, ⑩ 골든셋·화면·인용 품질·팝업 효과·배포 기록, ⑪ 의견 받기, ⑫ 팝업 캡처 |
| `docs/final-check-2026-10-29.md` | 고침 | 머리 메모, #98·09:30·10:48 행, 오후 4차·16:06 배포·문서 2차 행 |
| `docs/final-docs-inventory.md` | 고침 | 이 §0, 새 파일 2행, 개수 |
| `docs/presentation-kit/README.md` | 고침 | 슬라이드 14·시범 장 |
| `docs/presentation-kit/demo-script.md` | 고침 | 머리 메모, ① 정책 근거 행(새 판·이전 판), ④ 다시 넣기 행 |
| `docs/presentation-kit/limitations.md` | 고침 | 화면 행, 정책 근거·배포 기록 행 |
| `docs/presentation-kit/qna.md` | 고침 | "정책적 중요도가 빈칸으로 나오지 않나?" 문답 |
| `docs/presentation-kit/summary.md` | 고침 | 해결 흐름 ①, 검증·시범·측정 줄, 남은 과제 |
| `docs/history/README.md` | 고침 | 갱신 시각·목록 위치, screens·deploys 행 |
| `docs/history/timeline.md` | 고침 | 16:06 배포·#111·문서 2차 행(#110 행은 #110 에서) |
| `docs/history/metrics.md` | 고침 | 10-29 #110 행 |
| `docs/history/lessons.md` | 고침 | ④ 단추 못 찾음·실제 브라우저 axe·배포 기록 반영 PR 세 행 |
| `docs/history/deploys/README.md` | 고침 | 반영 PR 알려진 문제, 배포 12회 목록 |
| `docs/history/decisions/0017-…`·`0037-…`·`0040-…` | 고침(상태 한 줄) | ADR 0052 로 바뀐 부분 표시(본문은 그대로) |
| `docs/status.d/feat-policy-l2.md` | 고침(이후 변경 한 줄) | [추천 받기] → 팝업 |
| `docs/history/decisions/0052-policy-popup-preselect.md` | 최신(새 파일, #110) | ADR |
| `docs/history/deploys/2026-10-29-1606.md` | 최신(새 파일, #111) | 16:06 배포 기록 + 배포 뒤 확인 |

손대지 않은 것과 이유: 연표 조각(`timeline.d/`)·지표 조각(`metrics.d/`)·진행 조각(`progress.d/`)·레인 조각(`status.d/` 나머지)·측정 보고서(`docs/eval-*`)·
작업 일지(`overnight-*`)·지난 판단 기록(`final-check-2026-10-2{7,8}`)·지난 배포 기록은 그 시점 기록이라 1차 분류(최신=기록으로 정확, 또는 보관) 그대로다.
`tests/fixtures/*/README.md`·`docs/mcp.md`·`docs/external-apis.md`·`docs/korail-web-crawl.md`·`docs/vision-manifest.md`·`CONTRIBUTING.md`·PR 양식은 오후 변경과
관계없어 그대로다(CONTRIBUTING 의 "squash 금지" 와 실제 병합 방식이 다른 점은 `docs/status.md` §3.2 에 적고 규칙은 바꾸지 않았다).

## 문서 사이에 서로 달랐던 사실과 맞춘 값 (1차)

| 사실 | 달랐던 곳 | 맞춘 값(근거) |
|---|---|---|
| 초안 작성 방식 | README·presentation-kit·history README·architecture §4.6·ADR 0007: 로컬 Qwen 7B 작성 + Argon 1차 검토 | Argon 먼저 작성 → 규칙 검사 → L2 로컬 2차 검토, 로컬은 Argon 오류 응답 때만(ADR 0032·0038·0040, `config/llm.yaml writer: gemini·first_pass: off·local_check: on`). 옛 서술은 "이전 방식" 표시 |
| 외부 공개 | deploy/README·deploy-exposure·architecture·qna·limitations: Cloudflare Tunnel + Access(결정) 또는 "결정 대기", deploy-exposure "tailscale funnel 쓰지 않음" | 2026-10-28 부터 Tailscale Funnel `rra.taile5afcf.ts.net` + 앱 로그인(pilot-guide, 배포 기록, `config/api.yaml`) → ADR 0047 로 사후 기록, Cloudflare 는 이전 계획 |
| 로컬 2차 검토 | pilot-guide §6.5 "켜기·섹션당 20초 상한" | 기본 on·시간 상한 없음(ADR 0038·0040, `llm.yaml local_check: on`) |
| 측정 문서 | status.md §6 "측정 docs/eval-2026-10-29-pilot3.md" | 그 파일은 없음(3차 전체 측정 중단) → 레인 측정 `eval-2026-10-29-draft-first.md` + 배포 확인 기록 |
| 운영 DB 재분류 | CLAUDE.md·pending.md "배포 뒤 이주" | 2026-10-29 09:3x 적용 완료 340행(`docs/history/deploys/2026-10-29-0930.md`) |
| 유사과제 적중 | timeline "9/10 → 6/10", status "5/10 → 9/10" | 둘 다 맞음 — 9/10(10-27) → 적재 뒤 6/10(`rra eval`)·같은 코퍼스 5/10 → 수정 9/10(`eval-2026-10-28-precheck.md`). 보고서 재료 ⑧ 에 순서대로 적음 |
| 테스트 수 | summary 1,495(10-27)·history README 1,178(10-26) | pytest 2,406 · vitest 159 · e2e 29(+3 skip) (#99, 2026-10-29) |
| 자료 건수 | summary·limitations·history README: own 1,119 / alio 120 / openalex 2,482 / scienceon 2,045 | 운영 DB 2026-10-29 09:37 집계 16,100건(보고서 재료 ⑤) |
| ADR 목록 | decisions/README 가 0028 까지 | 0029~0051 추가(0047 Funnel 사후 기록, 0048~0051 UI 레인 초안) |
| 테스트 수(UI 뒤) | #99 2,406·vitest 159·e2e 29 | pytest 2,418 · vitest 201 · e2e 40(+3 skip) (#108) |
| 로그인 화면 | pilot-guide·web/README: `/login` 페이지·"오른쪽 위 로그아웃" | 로그인 페이지 없음(홈 카드·화면 안 창), 로그아웃은 사이드바 사용자 칸(ADR 0048) |

## 저장소 루트·배포 (6)

| 파일 | 분류 | 메모 |
|---|---|---|
| `.github/pull_request_template.md` | 최신 | PR 양식 — 그대로 |
| `CLAUDE.md` | 고침 | Funnel(ADR 0047)·운영 DB 재분류 완료·7B 이전 방식 표시·Research Studio·문서 최신화 줄 |
| `CONTRIBUTING.md` | 최신 | 규칙(브랜치·조각 파일·데이터 위치) 현재와 같음 |
| `README.md` | 고침 | 현재 상태 2026-10-29·작성 방식(Argon 먼저)·문서 안내 갱신, 2026-10-26 상태는 접어 둠 |
| `deploy/README.md` | 고침 | 외부 공개 = Tailscale Funnel, Cloudflare 터널은 이전 계획 표시, mlx 역할 |
| `web/README.md` | 고침 | Research Studio 화면 틀·파일 위치 단락, "1차 검토" 이전 방식 표시, Lighthouse /login 메모 |

## docs 본문 (16)

| 파일 | 분류 | 메모 |
|---|---|---|
| `docs/architecture.md` | 고침 | 머리 현재 상태 메모·§4.6 이전 방식 표시·§4.25 10-28~29 변경 요약·G·§10 표시 |
| `docs/deploy-exposure.md` | 고침 | 머리에 현재 운영(Funnel)·"funnel 쓰지 않음"은 당시 계획 표시 |
| `docs/external-apis.md` | 고침 | 머리에 NTIS IP 차단(10-28~29) 메모 |
| `docs/final-check-2026-10-27.md` | 낡음(보관) · 표시 추가 |  |
| `docs/final-check-2026-10-28.md` | 최신(측정·판단 기록) | 판단 기록(10-28) — 의견 1~25 원본 |
| `docs/final-check-2026-10-29.md` | 최신(측정·판단 기록) | 판단 기록(10-29 3차) |
| `docs/final-docs-inventory.md` | 고침(새 파일) | 새 파일 — 이 목록 |
| `docs/final-report-materials.md` | 고침(새 파일) | 새 파일 — 최종보고서 재료 ①~⑫ |
| `docs/korail-web-crawl.md` | 최신 | 수집 기록(10-27) |
| `docs/llm-bench-2026-10-26.md` | 낡음(보관) · 표시 추가 |  |
| `docs/mcp.md` | 최신 | MCP 도구·보안 — 그대로 |
| `docs/overnight-2026-10-27.md` | 낡음(보관) · 표시 추가 |  |
| `docs/overnight-2026-10-28.md` | 최신(측정·판단 기록) | 작업 일지(10-28, 레인 표) — 기록 |
| `docs/pilot-guide.md` | 고침 | Cloudflare 주소 이전 계획·§1 화면 안 로그인·§2 화면 구성(Research Studio)·NTIS 10-29·배포 뒤 시간·L2 설정 행 |
| `docs/status.md` | 고침 | §0 지금 상태 요약(운영 c277253·화면 Research Studio), 공개 방식·NTIS·웹 행, 3차 통합·UI·문서 최신화 행, 없는 측정 파일 참조 정정 |
| `docs/vision-manifest.md` | 최신 | 판독 입력 형식 |

## docs 측정 기록(eval) (18)

| 파일 | 분류 | 메모 |
|---|---|---|
| `docs/eval-2026-10-27.md` | 낡음(보관) · 표시 추가 |  |
| `docs/eval-2026-10-28-argon-live.md` | 최신(측정·판단 기록) |  |
| `docs/eval-2026-10-28-figure-edit.md` | 최신(측정·판단 기록) |  |
| `docs/eval-2026-10-28-figures-v2.md` | 낡음(보관) · 표시 추가 |  |
| `docs/eval-2026-10-28-figures-wide.md` | 최신(측정·판단 기록) |  |
| `docs/eval-2026-10-28-figures.md` | 낡음(보관) · 표시 추가 |  |
| `docs/eval-2026-10-28-hwpx-format.md` | 최신(측정·판단 기록) |  |
| `docs/eval-2026-10-28-pilot-fixes.md` | 최신(측정·판단 기록) |  |
| `docs/eval-2026-10-28-pilot2.md` | 최신(측정·판단 기록) | 최근 전체 측정(10-29 01:55) |
| `docs/eval-2026-10-28-policy-reclass.md` | 최신(측정·판단 기록) |  |
| `docs/eval-2026-10-28-precheck-v2.md` | 낡음(보관) · 표시 추가 |  |
| `docs/eval-2026-10-28-precheck-v3.md` | 최신(측정·판단 기록) |  |
| `docs/eval-2026-10-28-precheck.md` | 낡음(보관) · 표시 추가 |  |
| `docs/eval-2026-10-28.md` | 낡음(보관) · 표시 추가 |  |
| `docs/eval-2026-10-29-draft-first.md` | 최신(측정·판단 기록) |  |
| `docs/eval-2026-10-29-evidence-scope.md` | 최신(측정·판단 기록) |  |
| `docs/eval-2026-10-29-figure-phrases.md` | 최신(측정·판단 기록) |  |
| `docs/eval-2026-10-29-precheck-series.md` | 최신(측정·판단 기록) |  |

## docs/presentation-kit·ocr-sample (6)

| 파일 | 분류 | 메모 |
|---|---|---|
| `docs/ocr-sample/summary.md` | 최신 | OCR 견본 집계 |
| `docs/presentation-kit/README.md` | 고침 | 슬라이드 3·5·8·14 갱신, 시범 장 추가 |
| `docs/presentation-kit/demo-script.md` | 고침 | 머리에 지금과 다른 곳 메모 |
| `docs/presentation-kit/limitations.md` | 고침 | 현재 표 추가, 해결된 줄 표시 |
| `docs/presentation-kit/qna.md` | 고침 | 외부 전송·판정·비용·운영 답 갱신(이전 답은 괄호) |
| `docs/presentation-kit/summary.md` | 고침 | 2026-10-29 수치·흐름으로 다시 씀(10-27 판은 접어 둠) |

## docs/history (README·연표·수치·교훈) (4)

| 파일 | 분류 | 메모 |
|---|---|---|
| `docs/history/README.md` | 고침 | 최신 요약 위치·deploys 행 |
| `docs/history/lessons.md` | 최신 |  |
| `docs/history/metrics.md` | 고침 | 요약표 10-27~10-29 행·읽는 법 |
| `docs/history/timeline.md` | 고침 | 제목 기간·10-29 세 행(#99·배포, Research Studio, 문서 최신화) |

## docs/history/decisions (ADR) (53)

| 파일 | 분류 | 메모 |
|---|---|---|
| `docs/history/decisions/0001-hexagonal-and-security-rules.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0002-no-microservices-keep-sqlite.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0003-qwen-3b-to-7b.md` | 낡음(보관) · 표시 추가 |  |
| `docs/history/decisions/0004-overlap-keyword-condition.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0005-relevance-floor-0_79.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0006-keep-qwen-after-bench.md` | 고침 | 상태 줄(역할 바뀜) |
| `docs/history/decisions/0007-local-compose-plus-argon-review.md` | 낡음(보관) · 표시 추가 |  |
| `docs/history/decisions/0008-web-react-spa.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0009-own-data-visibility-public.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0010-source-diversity-min-per-source-6.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0011-six-step-flow-final-review-once.md` | 고침 | 상태 줄(1차 검토 끔) |
| `docs/history/decisions/0012-project-recommendations.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0013-draft-quality-eight-measured.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0014-ci-automerge.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0015-web-frontend-stack.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0016-scienceon-patents-vs-kipris.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0017-usability-review-reflected.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0018-image-vision-trust-rules.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0019-policy-crawl-snapshot-and-scope.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0020-ntis-live.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0021-policy-sources-scope.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0022-table-facts-and-term-candidates.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0023-rnd-notice-source.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0024-exposure-cloudflare-tunnel-access.md` | 낡음(보관) · 표시 추가 |  |
| `docs/history/decisions/0025-source-ip-policy.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0026-login-staff-guest.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0027-draft-fallback.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0028-overlap-project-sources-only.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0029-proposal-figures.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0030-figure-edit-via-spec.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0031-live-search.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0032-argon-first.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0033-figures-v2-as-is-to-be-techniques.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0034-hwpx-format-levels.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0035-run-step-navigation-regenerate.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0036-precheck-judgment-and-choices.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0037-edit-ai-buttons.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0038-ai-wait-cancel.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0039-precheck-table-first-cards.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0040-policy-reclass-docrefs-local-review.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0041-figures-wide-body-width.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0042-status-marks-and-step-bar.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0043-precheck-series-rows.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0044-figure-phrases-not-truncated.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0045-draft-first-figures-background.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0046-evidence-scope-admin-status.md` | 최신(ADR 기록) |  |
| `docs/history/decisions/0047-exposure-tailscale-funnel.md` | 고침(새 파일) | 새 ADR — Tailscale Funnel 사후 기록 |
| `docs/history/decisions/0048-in-screen-login-sidebar-frame.md` | 고침(새 파일) | 새 ADR — UI 레인 1 초안 |
| `docs/history/decisions/0049-research-home-progress.md` | 고침(새 파일) | 새 ADR — UI 레인 2 초안 |
| `docs/history/decisions/0050-global-search-doc-api.md` | 고침(새 파일) | 새 ADR — UI 레인 3 초안 |
| `docs/history/decisions/0051-design-tokens.md` | 고침(새 파일) | 새 ADR — UI 레인 4 초안 |
| `docs/history/decisions/0052-policy-popup-preselect.md` | 최신(새 파일, 2차) | ① 정책 근거 팝업·다시 넣는 길(#110) |
| `docs/history/decisions/README.md` | 고침 | ADR 0029~0051 목록, 이전 방식 표시 · 2차: 0052 행(#110) |

## docs/history/deploys (14)

| 파일 | 분류 | 메모 |
|---|---|---|
| `docs/history/deploys/2026-10-28-1129.md` | 최신(기록) |  |
| `docs/history/deploys/2026-10-28-1141.md` | 최신(기록) |  |
| `docs/history/deploys/2026-10-28-1153.md` | 최신(기록) |  |
| `docs/history/deploys/2026-10-28-1202.md` | 최신(기록) |  |
| `docs/history/deploys/2026-10-28-1314.md` | 최신(기록) |  |
| `docs/history/deploys/2026-10-28-1511.md` | 최신(기록) |  |
| `docs/history/deploys/2026-10-28-1540.md` | 최신(기록) |  |
| `docs/history/deploys/2026-10-28-2014.md` | 최신(기록) |  |
| `docs/history/deploys/2026-10-29-0207.md` | 최신(기록) |  |
| `docs/history/deploys/2026-10-29-0930.md` | 최신(기록) | 09:30 배포 기록·DB 재분류·배포 뒤 확인(#100) |
| `docs/history/deploys/2026-10-29-1048.md` | 고침(새 파일) | 10:48 Research Studio 배포 기록 + 배포 뒤 확인(통합 담당 10:5x)·#108 수정 2건 |
| `docs/history/deploys/2026-10-29-1606.md` | 최신(새 파일, 2차) | 16:06 정책 근거 팝업 배포 기록 + 배포 뒤 확인, 반영 PR 손으로 고침(#111) |
| `docs/history/deploys/README.md` | 고침(2차) | 반영 PR 알려진 문제·배포 목록 |
| `docs/history/deploys/pending.md` | 고침(2차) | 16:06 배포로 비워진 뒤 #112(작성 가이드 화면 글) 한 줄 |

## 조각 파일 (status.d·progress.d·timeline.d) (112)

| 파일 | 분류 | 메모 |
|---|---|---|
| `docs/history/progress.d/feat-draft-fallback.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-draft-first-figures-bg.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-edit-ai.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-evidence-scope.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-figure-phrases.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-figures-v2.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-figures-wide.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-format-ui.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-login.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-ntis-live.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-policy-crawl.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-policy-l2.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-policy-sources.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-policy-vision.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-precheck-flow.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-precheck-series.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-precheck-v3.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-rnd-notice.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-scienceon-live.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-source-ip.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-table-facts-terms.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-usability.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-versions-nav.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/progress.d/feat-web-u9.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-feat-attachment-images.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-feat-data-dir.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-feat-draft-quality.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-feat-login.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-feat-ntis-live.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-feat-ntis-live2.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-feat-photo-filter.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-feat-policy-crawl.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-feat-policy-sources.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-feat-policy-vision.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-feat-rnd-notice.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-feat-scienceon-live.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-feat-source-ip.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-feat-table-facts-terms.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-feat-tunnel.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-feat-usability.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-feat-web-ntis.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-feat-web-u9.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-feat-web.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-fix-eval-findings.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-fix-image-vision-basis.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-fix-reranker-lock.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-27-fix-xlsx-sheet-text.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-28-chore-ai-wait-cancel.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-28-feat-argon-first.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-28-feat-draft-fallback.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-28-feat-edit-ai.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-28-feat-eval-argon-live.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-28-feat-figure-edit-spec.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-28-feat-figures-v2.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-28-feat-figures-wide.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-28-feat-format-ui.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-28-feat-live-search.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-28-feat-overlap-sources.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-28-feat-policy-l2.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-28-feat-precheck-flow.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-28-feat-precheck-v3.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-28-feat-versions-nav.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-28-feat-web-argon-live.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-28-fix-figure-local-slot.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-29-feat-draft-first-figures-bg.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-29-feat-evidence-scope.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-29-feat-figure-phrases.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/history/timeline.d/2026-10-29-feat-precheck-series.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/chore-ai-wait-cancel.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-argon-first.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-data-dir.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-draft-fallback.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-draft-first-figures-bg.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-draft-quality.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-edit-ai.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-eval-argon-live.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-evidence-scope.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-figure-edit-spec.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-figure-phrases.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-figures-v2.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-figures-wide.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-format-ui.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-live-search.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-login.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-ntis-live.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-ntis-live2.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-overlap-sources.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-pilot-password.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-policy-crawl.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-policy-l2.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-policy-sources.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-policy-vision.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-precheck-flow.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-precheck-series.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-precheck-v3.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-proposal-figures.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-rnd-notice.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-scienceon-live.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-source-ip.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-table-facts-terms.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-tunnel.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-ui-studio-frame.md` | 최신(UI 조각 — status·timeline·ADR 0048~0051 에 모음 완료) |  |
| `docs/status.d/feat-ui-studio-home.md` | 최신(UI 조각 — status·timeline·ADR 0048~0051 에 모음 완료) |  |
| `docs/status.d/feat-ui-studio-search.md` | 최신(UI 조각 — status·timeline·ADR 0048~0051 에 모음 완료) |  |
| `docs/status.d/feat-ui-studio-tokens.md` | 최신(UI 조각 — status·timeline·ADR 0048~0051 에 모음 완료) |  |
| `docs/status.d/feat-usability.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-versions-nav.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-web-argon-live.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-web-ntis.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-web-u9.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/feat-web.md` | 최신(조각 — status·timeline 에 모음 완료) |  |
| `docs/status.d/fix-image-vision-basis.md` | 최신(조각 — status·timeline 에 모음 완료) |  |

## tests fixture 설명 (5)

| 파일 | 분류 | 메모 |
|---|---|---|
| `tests/fixtures/alio/README.md` | 최신(fixture 설명) |  |
| `tests/fixtures/kipris/README.md` | 최신(fixture 설명) |  |
| `tests/fixtures/llm/README.md` | 최신(fixture 설명) |  |
| `tests/fixtures/ntis/README.md` | 최신(fixture 설명) |  |
| `tests/fixtures/scienceon/README.md` | 최신(fixture 설명) |  |

## src 프롬프트(코드) (25)

| 파일 | 분류 | 메모 |
|---|---|---|
| `src/rra/adapters/llm/prompts/brief.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/clarify.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/differentiate.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/figure_edit.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/figure_techniques.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/figures.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/json_fallback.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/outline.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/recommend.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/review.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/section_expected_management.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/section_expected_standing.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/section_expected_technology.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/section_method.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/section_objective.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/section_overlap_review.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/section_policy_importance.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/section_strategy_alignment.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/section_task_type.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/section_tech_importance.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/section_title.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/section_utilization.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/structure.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/system.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
| `src/rra/adapters/llm/prompts/vision.md` | 최신(코드 일부 — 프롬프트, 대상 아님) |  |
