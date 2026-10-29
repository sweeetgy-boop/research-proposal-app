# 문서 목록과 분류 (2026-10-29, docs/final-docs)

저장소의 md 파일 249개(이 파일 포함). 분류: **최신**(지금 사실과 맞음 — 날짜 붙은 기록은 그 시점 기록으로 정확),
**고침**(이번에 고침), **낡음(보관)**(이전 방식·지난 계획 — 지우지 않고 머리에 "보관" 표시, 지금 사실은 표시한 파일에서 본다).
집계: 고침 23 · 낡음(보관) 12 · 최신 214.
UI 레인(Research Studio)이 남길 조각 `docs/status.d/feat-ui-studio-*.md` 와 화면 문구 반영은 UI 배포 뒤 이 목록에 더한다.

## 문서 사이에 서로 달랐던 사실과 맞춘 값

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
| ADR 목록 | decisions/README 가 0028 까지 | 0029~0047 추가 |

## 저장소 루트·배포 (6)

| 파일 | 분류 | 메모 |
|---|---|---|
| `.github/pull_request_template.md` | 최신 | PR 양식 — 그대로 |
| `CLAUDE.md` | 고침 | Funnel(ADR 0047)·운영 DB 재분류 완료·7B 이전 방식 표시·문서 최신화 줄 |
| `CONTRIBUTING.md` | 최신 | 규칙(브랜치·조각 파일·데이터 위치) 현재와 같음 |
| `README.md` | 고침 | 현재 상태 2026-10-29·작성 방식(Argon 먼저)·문서 안내 갱신, 2026-10-26 상태는 접어 둠 |
| `deploy/README.md` | 고침 | 외부 공개 = Tailscale Funnel, Cloudflare 터널은 이전 계획 표시, mlx 역할 |
| `web/README.md` | 고침 | 웹 구조 — Research Studio 반영은 UI 배포 뒤(진행 중), "1차 검토" 는 이전 방식으로 표시 |

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
| `docs/pilot-guide.md` | 고침 | Cloudflare 주소 이전 계획·화면 전환 진행 중·NTIS 10-29·배포 뒤 시간·L2 설정 행 |
| `docs/status.md` | 고침 | §0 지금 상태 요약 추가, 공개 방식·NTIS·웹 행, 3차 통합·배포·문서 최신화 행, 없는 측정 파일 참조 정정 |
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
| `docs/history/timeline.md` | 고침 | 제목 기간·10-29 두 행(#99·배포, 문서 최신화) |

## docs/history/decisions (ADR) (48)

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
| `docs/history/decisions/README.md` | 고침 | ADR 0029~0047 목록, 이전 방식 표시 |

## docs/history/deploys (12)

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
| `docs/history/deploys/README.md` | 최신(기록) |  |
| `docs/history/deploys/pending.md` | 최신(기록) | 09:30 배포로 비워짐(#100) |

## 조각 파일 (status.d·progress.d·timeline.d) (109)

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
| `docs/status.d/feat-ui-studio-tokens.md` | 최신(UI 조각 — UI 배포 뒤 모음 대기) |  |
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
