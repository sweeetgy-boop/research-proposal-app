# web — 연구과제 제안서 작성 보조 프론트엔드

Vite + React 19 + TypeScript(strict) SPA. 백엔드(FastAPI, `rra api`)가 `web/dist` 를 같은 출처로 서빙한다
(`settings.static_dir`, 기본 `web/dist`; 없으면 `/` 는 404). 흐름은 기획서 ①~⑥ 과 같다:
① 아이디어 입력 → ② 유사과제 확인(차별화 제안·과제 추천) → ③ 보강 질문 → 초안 생성(SSE 진행) → 초안 보기(v1/v2·근거·1차 검토) →
④ 직접 수정(DraftEditor) → 버전·비교·복원 → ⑤ 최종 검토 → ⑥ 최종 마무리(선택형 확정·제안자 정보·HWPX 내려받기·다시 열기).
그 밖에 run 목록·자료 검색·자료원 상태.

## 준비·실행

```bash
cd web && npm ci                 # Node 22+
npm run dev                      # 127.0.0.1:5173, /v1·/healthz 는 127.0.0.1:8000 으로 프록시
# 다른 터미널: 백엔드 (가짜 모드면 모델·DB 없이 즉시 응답)
RRA_FAKE_LLM=1 RRA_API_TOKEN=<토큰> ../.venv/bin/rra api
```

운영 빌드: `npm run build` → `web/dist`. 백엔드를 그대로 띄우면 `http://127.0.0.1:8000/` 에서 열린다 (별도 정적 서버·CORS 없음).

| 스크립트 | 하는 일 |
|---|---|
| `npm run dev` / `build` / `preview` | 개발 서버 / 빌드(`tsc -b && vite build`) / `vite preview`(4173) |
| `npm run lint` / `typecheck` | ESLint(`dangerouslySetInnerHTML` 금지 규칙 포함) / `tsc -b --noEmit` |
| `npm test -- --run` | Vitest + Testing Library + axe-core (CI 가 돌린다) |
| `npm run e2e` | Playwright. 가짜 백엔드가 `web/dist` 를 서빙하는 상태로 ①→⑥ 전체 흐름·키보드·화면 캡처. **먼저 `npm run build`**. 백엔드 실행 파일은 `RRA_BIN`(기본 `../.venv/bin/rra`), 포트 `RRA_E2E_PORT`(8010). `RRA_SCREENS_DIR=…` 이면 화면 캡처, `RRA_VIDEO=1` 이면 녹화 |
| `npm run lighthouse` | `@lhci/cli` 가 `vite preview` 에 대해 `/login` 을 2회 측정(`lighthouserc.json`: 성능·접근성·모범 사례 ≥ 0.95, CLS ≤ 0.05). Chrome 이 없으면 Playwright 의 Chromium 을 쓴다. 백엔드가 필요 없어 로컬에서 돌린다(CI 에는 넣지 않았다 — 로그인 뒤 화면은 세션이 필요해 측정 범위가 로그인 화면뿐이기 때문) |
| `npm run gen:api` | `../docs/openapi.json` → `src/api/schema.d.ts`(커밋한다). 응답 타입은 스키마에 없어 `src/api/types.ts` 에 `entrypoints/views.py` 기준으로 손으로 둔다 |

## 구조

```
src/
  api/        client.ts(fetch 래퍼·CSRF·problem+json→ApiError) endpoints.ts(28 경로 중 사용분) hooks.ts(TanStack Query)
              sse.ts(이름 이벤트·지수 백오프 재접속) types.ts(응답 모양) schema.d.ts(생성)
  auth/       session.ts(CSRF 만 메모리+sessionStorage) RequireAuth.tsx
  components/ Layout(건너뛰기 링크·stepper·테마 토글) Stepper ProblemBanner EmptyState UntrustedText OriginBadge ScoreTable VirtualList
  components/ui/  shadcn 식 복사본(button·input·textarea·label·badge·card·alert·skeleton·checkbox·select) +
                  네이티브 구현(dialog=<dialog>.showModal, toast=aria-live, tabs=role 속성)
  features/idea/  store.ts(①~③ 입력, sessionStorage) IdeaForm AlertsTable RecommendationCards DifferentiationPanel
  features/draft/ editModel.ts(순수 편집 모델) DraftEditor ReviewPanel EvidenceChips
  features/versions/ DiffView(diff 패키지 글자 단위)
  routes/     Login Idea Precheck Clarify Runs Search Sources, run/(RunLayout Progress Draft Edit Versions FinalReview Finalize)
  lib/        sections.ts(섹션 제목·origin 라벨·상태 라벨) validation.ts(백엔드와 같은 규칙·문구) utils.ts
  test/       setup.ts utils.tsx(renderWithProviders·mockFetch·axe) fixtures/(가짜 백엔드 실응답)
e2e/          flow(①→⑥·추천 0건·보강 질문 0개·목록/검색/자료원·CSP 콘솔) keyboard(건너뛰기·포커스 링·Esc) screens(캡처)
public/       theme-init.js(첫 그리기 전 테마, 인라인 금지라 외부 파일) favicon.svg
```

디자인 토큰은 `src/index.css` 의 CSS 변수(`--background`·`--primary`·`--origin-*` …, hsl)로 두고 Tailwind v4 `@theme inline` 으로 연결한다.
다크 테마는 `prefers-color-scheme` 기본 + `data-theme` 수동 전환(localStorage `rra-theme`). `prefers-reduced-motion` 이면 애니메이션·전환을 끈다.
글꼴은 `pretendard` npm 의 가변·동적 서브셋을 번들에 넣는다(외부 요청 없음).

## 보안

- 토큰은 로그인 때 한 번 `POST /v1/session` 본문으로만 보내고 **저장하지 않는다**. 세션은 httpOnly·SameSite=Strict 쿠키, JS 는 CSRF 만 들고
  상태 변경 요청에 `X-RRA-CSRF` 를 붙인다. 401 이면 세션을 비우고 로그인으로.
- 초안·검토 의견·청크·추천은 비신뢰 텍스트 — `UntrustedText`(텍스트 노드)로만 그린다. `dangerouslySetInnerHTML` 은 ESLint 가 막는다.
- 제안자 정보(성명·직급·연락처)는 최종 마무리 화면의 메모리에만 있고 `POST /v1/runs/{id}/finalize` 본문으로만 나간다(e2e 가 저장소에 없음을 확인).
- 편집 임시 저장은 서버 `PUT /v1/runs/{id}/draft/working`(1.5초 디바운스), localStorage 에 두지 않는다.
- CSP(`script-src 'self'; style-src 'self'`) 호환: 빌드 산출물에 인라인 `<script>`·`style=` 없음(`dist/index.html` 확인), React 는 CSSOM 으로
  스타일을 넣으므로 `style` prop 은 동작한다. Radix 는 `<style>` 을 주입해 쓰지 않는다(ADR 0015).

## 접근성·성능 점검 (2026-10-27 측정)

| 항목 | 목표 | 측정 |
|---|---|---|
| Lighthouse(desktop, `/login`, 2회) | 성능·접근성·모범 사례 ≥ 95 | **100 / 100 / 100**, CLS 0, LCP 0.7 s, TBT 0 ms |
| axe-core(WCAG 2.x A/AA + best-practice, jsdom) | 위반 0 | **0** — IdeaForm·DraftEditor·로그인·유사과제 확인·초안 보기·최종 마무리·run 목록 |
| JS 번들(gzip) | ≤ 200 KB | 초기 110.6 KB(index 82.2 + react 15.0 + query 13.4), 경로 청크 합계 ≈ 56 KB(전체 ≈ 167 KB), CSS 21.2 KB |
| 키보드 | 전부 조작 가능 | 건너뛰기 링크→main, 보이는 포커스 링(`:focus-visible`), Esc 로 대화상자 닫힘, 탭 화살표 이동(e2e) |
| 반응형 | 360 px 가로 스크롤 없음 | e2e 가 `scrollWidth ≤ clientWidth` 확인(초안 화면·다크) |
| 긴 목록 | 가상화 | 초안 문장 60행·편집 80행 초과, 버전 목록 — `@tanstack/react-virtual` |
| 테스트 | — | Vitest 33(6 파일), Playwright 8 시나리오(①→⑥ 파일 내려받기·추천 0건·보강 질문 0개·목록/검색/자료원·CSP 콘솔 오류 0·키보드·Esc·캡처) |

## 자체 디자인 검토 (2회)

1. 일관성: 간격(섹션 `space-y-6`, 카드 `p-4/5`)·제목 크기(h1 2xl, h2 lg, h3 base)·배지 색(origin 토큰 4색)을 맞췄고, 스크롤 컨테이너 안의
   `sr-only` 가 문서 폭을 늘리던 문제(360 px 가로 스크롤)를 `relative` 로 고쳤다. 긴 선택지 라벨 배지는 줄바꿈 허용.
2. 빈·로딩·오류 상태: 모든 조회에 Skeleton(높이 예약)·EmptyState·ProblemBanner(problem+json detail) 를 두고, 문장이 없는 섹션에는 사유와
   다음 행동("직접 수정에서 채울 수 있습니다")을 적었다. 토스트는 오류만 `role=alert`, 나머지는 polite. 한국어 문구는 백엔드 검증 문구와 같게
   ("필수 슬롯이 비었습니다: …", "슬롯 길이 n > 2000").
