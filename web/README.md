# web — 연구과제 제안서 작성 보조 프론트엔드

Vite + React 19 + TypeScript(strict) SPA. 백엔드(FastAPI, `rra api`)가 `web/dist` 를 같은 출처로 서빙한다
(`settings.static_dir`, 기본 `web/dist`; 없으면 `/` 는 404). 흐름은 기획서 ①~⑥ 과 같다:
① 아이디어 입력(간편 입력 → 네 칸 미리보기·보완 질문 / 상세 입력 4칸, 정책 근거 추천 팝업 — ADR 0052) → ② 유사과제 확인(차별화 제안·과제 추천·차별성
비교표) → 선행연구 브리핑(우선 근거 선택) → ③ 보강 질문 → 초안 생성(SSE 진행) → 초안 보기(v1·근거 패널·로컬 2차 검토 — v1/v2·1차 검토는 이전 방식) →
④ 직접 수정(DraftEditor + 섹션 AI 다시 쓰기·보완 질문) → 버전·비교·복원 → ⑤ 최종 검토 → 제출 전 점검(사용 기록·만족도) →
⑥ 최종 마무리(선택형 확정·제안자 정보·HWPX 내려받기·다시 열기). 그 밖에 내 제안서 목록·자료 검색·자료 현황.

**Research Studio 화면 틀**(배포됨 (c277253, 2026-10-29 10:48), ADR 0048~0051):
- 틀: 왼쪽 사이드바 `components/frame/Sidebar.tsx`(메뉴·저장 안내·사용자 칸·테마), 위쪽 막대 `frame/TopBar.tsx`(경로 표시 `frame/crumbs.ts`·통합 검색),
  1024px 미만 접는 메뉴 `frame/MobileMenu.tsx`(native `<dialog>`). 앱 이름은 탭 제목·사이드바·경로 첫 칸 "Research Studio".
- 로그인: 로그인 페이지 없음 — `features/auth/LoginCard`·`LoginDialog`(`LoginDialogProvider` 하나)·`useRequireLogin()`, 보호 화면은 주소 그대로 그 자리에 창.
- 홈 `/`: `routes/Home.tsx` + `features/home/**`(히어로·연구 한눈에 보기·작성 팁·최근 제안서 표·시작 안내, 진행률·칩 `runView.ts`), 로그인 전 API 0건.
- 작성 가이드 `/guide`: `routes/Guide.tsx` + `features/guide/content.tsx`(`docs/pilot-guide.md` §2~§5.5 와 함께 고친다).
- 통합 검색: `features/globalsearch/GlobalSearch.tsx`(⌘K/Ctrl+K, combobox·두 묶음), 자료는 `GET /v1/search/docs`, 자료 검색 `routes/Search.tsx`(주소가 상태).
- 디자인 토큰: `src/index.css` 한 곳(색·모서리·여백·다크), 공용 조각 `components/ui/{eyebrow,status-chip,progress-bar}.tsx`. 새 화면은 토큰만 쓴다.
  명암비 표는 `docs/status.d/feat-ui-studio-tokens.md`.

**정책 근거 팝업과 다시 넣는 길**(배포됨 36e0709, 2026-10-29 16:06, ADR 0052):
- ① `features/idea/PolicyPickDialog.tsx` — 네 칸이 상세 입력에 채워질 때(`QuickInput onFilled`) 또는 정책 근거가 빈 채 [다음](`Idea.onSubmit`)에 열림.
  열리면 `fetchPolicySuggestions`(`api/policySuggestions.ts`, 응답 `rank` 순 정렬) 자동 호출, `rank` 1 미리 체크·"기본 추천" 배지, [다시 받기] 는
  `exclude_doc_ids`(본 문서)로 더 받아 아래에 붙임, [적용] → `mergePolicyBasis`(같은 줄 한 번) / [나중에 넣기] → `IdeaState.policyDeferred`(다시 묻지 않음).
  정책 근거 칸은 `IdeaForm` 의 접지 않는 상자 + `policyTools` 자리([정책 근거 추천 열기]·안내). run 안 ① 다시 열기(`RunIdea`)도 같은 팝업.
- ③ `routes/Clarify.tsx` — 정책 근거가 비면 `PolicyCards` 를 처음부터 펼침. 초안 보기 `routes/run/Draft.tsx` 의 빈 2-가-(1) → `../edit?policy=1`.
- ④ `routes/run/Edit.tsx` — 2-가-(1) 머리 [정책 근거 넣기·바꾸기] 늘 보임(비면 주 색, 편집 불가면 대화상자에 이유), 빈칸 안내 줄 `data-testid=policy-empty`,
  `?policy=1` 이면 대화상자를 열고 주소에서 지움. `features/policy/RunPolicyDialog.tsx` 직접 입력 → `withManual`/`editedChoice`(`features/policy/model.ts`).
- ⑥ `routes/run/SubmitCheck.tsx` — "정책 근거" 항목(`policy_basis`)이 확인 필요면 [정책 근거 넣기] → `/edit?policy=1`.
- 접근 이름: `DocRef` 는 "제목 · 자료원 근거 보기", 제출 전 점검 항목 단추는 보이는 글자 + 숨은 "— 이동"(WCAG 2.5.3).

시험: vitest 214 · e2e 43(+3 skip)(#110). e2e 는 [다음] 뒤 팝업을 `helpers.goPrecheck`(뜨면 [나중에 넣기])로 넘기고, `policy-popup.spec.ts` 는 axe-core 를
페이지에 넣어 실제 브라우저 접근성을 본다(이 spec 만 `bypassCSP`, 애니메이션 끝난 뒤 검사).

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

e2e 백엔드를 **다른 체크아웃의 코드**로 띄우려면 `RRA_BIN` 에 여러 단어를 줄 수 있다(셸 문자열로 들어간다):
`RRA_BIN="env PYTHONPATH=/path/to/src /path/to/.venv/bin/python -m rra.entrypoints.cli" CI=1 npm run e2e`.

## 구조

```
src/
  api/        client.ts(fetch 래퍼·CSRF·problem+json→ApiError) endpoints.ts(41 경로 중 사용분) hooks.ts(TanStack Query)
              sse.ts(이름 이벤트·지수 백오프 재접속) types.ts(응답 모양) schema.d.ts(생성)
              policySuggestions.ts(정책 근거 추천 — 요청 본문·rank 정렬·formatPolicyQuote·mergePolicyBasis, 모양이 바뀌면 이 파일만)
  auth/       session.ts(CSRF 만 메모리+sessionStorage) RequireAuth.tsx
  components/ Layout(건너뛰기 링크·stepper·테마 토글) Stepper ProblemBanner EmptyState UntrustedText OriginBadge ScoreTable VirtualList
  components/ui/  shadcn 식 복사본(button·input·textarea·label·badge·card·alert·skeleton·checkbox·select) +
                  네이티브 구현(dialog=<dialog>.showModal, toast=aria-live, tabs=role 속성)
  features/idea/  store.ts(①~③ 입력·브리핑 선택, sessionStorage) IdeaForm(policyTools 자리) QuickInput(간편 입력) PolicyPickDialog(정책 근거 팝업) ComparisonTable
                  AlertsTable RecommendationCards DifferentiationPanel
  features/brief/ BriefView(브리핑 10건·연도 CSS 막대·주제어·공백 후보)
  features/draft/ editModel.ts(순수 편집 모델) DraftEditor ReviewPanel EvidenceChips
  features/evidence/ EvidencePanel(<dialog> — 발췌·근거 수준·Argon 적합성·승인/교체/제외 → 새 버전, 409 재적재)
  features/rewrite/  SectionRewrite(현재·후보 나란히, 고른 행 반영) SectionQuestions(체크리스트 보완 질문·답 저장) model.ts
  features/policy/   PolicyCards(정책적 중요도 작성안) RunPolicyDialog(④ 대화상자·직접 입력) model.ts(합치기·직접 수정·withManual) store.ts(③ 고른 안)
  features/submit/   SubmitCheckList(항목 → target 이동) targets.ts(section:/sentence:/route: → 경로)
  features/versions/ DiffView(diff 패키지 글자 단위)
  routes/     Login Idea Precheck Brief Clarify Runs Search Sources,
              run/(RunLayout Progress Draft Edit Versions FinalReview SubmitCheck Finalize)
  lib/        sections.ts(섹션 제목·origin 라벨·상태 라벨) validation.ts(백엔드와 같은 규칙·문구) utils.ts
  test/       setup.ts utils.tsx(renderWithProviders·mockFetch·axe) fixtures/(가짜 백엔드 실응답)
e2e/          flow(①→⑥·추천 0건·보강 질문 0개·목록/검색/자료원·CSP 콘솔) keyboard(건너뛰기·포커스 링·Esc) screens(캡처)
              u9(간편 입력→비교표→브리핑→생성→근거 패널→다시 쓰기·보완 질문→최종 검토→제출 전 점검→HWPX→만족도, 503 대체)
              policy-popup(팝업 [적용] → 초안 2-가-(1) 채워짐 / [나중에 넣기] → ④ 다시 넣기 / ⑥ 바로가기, axe) 외 2026-10-28~29 spec 들
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

## 접근성·성능 점검 (2026-10-27 측정, U9 반영 뒤)

| 항목 | 목표 | 측정 |
|---|---|---|
| Lighthouse(desktop, `/login`, 2회, `vite preview`) | 성능·접근성·모범 사례 ≥ 95 | **100 / 100 / 100**, CLS 0, LCP 0.7 s, TBT 0 ms (10-27. 10-29 부터 `/login` 은 홈 + 로그인 창 — Research Studio 뒤 100·100·100·CLS 0.001 은 `docs/status.d/feat-ui-studio-tokens.md`) |
| Lighthouse(가짜 백엔드 `rra api` 가 서빙, `/login`) | 참고 | 98 / 100 / 100 (LCP 0.97 s — 백엔드가 gzip 을 주지 않아 `uses-text-compression`) |
| Lighthouse(로그인 뒤 화면) | 가능하면 | **측정 못 함** — 인증 게이트가 sessionStorage 의 CSRF 로 판단해 `lhci --settings.extraHeaders` 로 세션 쿠키만 주면 `/login` 으로 돌아간다. Playwright 기반 측정(playwright-lighthouse)은 외부 패키지라 넣지 않았다 |
| axe-core(WCAG 2.x A/AA + best-practice, jsdom) | 위반 0 | **0** — 기존 7 + 새 화면 8(간편 입력·정책 근거 추천·비교표·브리핑·근거 패널·다시 쓰기·보완 질문·제출 전 점검) |
| JS 번들(gzip) | ≤ 200 KB | 초기 111.6 KB(index 82.8 + react 15.4 + query 13.4), 경로 청크 합계 ≈ 72 KB(전체 ≈ 184 KB; Brief 2.9·SubmitCheck 3.7·Edit 8.4·Draft 6.5), CSS 21.4 KB |
| 키보드 | 전부 조작 가능 | 건너뛰기 링크→main, 입력 방식 라디오 화살표 이동, 보이는 포커스 링, `<dialog>` 포커스 가둠·Esc(근거 패널·다시 쓰기·보완 질문), 탭 화살표 이동(e2e) |
| 반응형 | 360 px 가로 스크롤 없음 | e2e 가 `scrollWidth ≤ clientWidth` 확인(초안·제출 전 점검, 다크). 비교표·다시 쓰기 표는 컨테이너 안 가로 스크롤 |
| 긴 목록 | 가상화 | 초안 문장 60행·편집 80행 초과, 버전 목록 — `@tanstack/react-virtual` (브리핑 10건·점검 9항목은 고정 길이라 가상화 없음) |
| 테스트 | — | (2026-10-27 기준) Vitest 50(13 파일), Playwright 10 시나리오. 지금(2026-10-29 #110): vitest 214(41 파일)·Playwright 43 통과 + 3 skip(캡처 전용) |

## U9 설계 메모 (2026-10-27)

- **간편 입력이 기본**(`store.inputMode`). 네 칸 미리보기 → 보완 질문 답은 `POST /v1/ideas/structure/merge`(LLM 없음) → "상세 입력에 채우기"
  로만 폼에 들어간다(자동 제출 없음). 503 이면 안내 뒤 상세 입력으로. 자유 문장은 sessionStorage 에만(개인정보 아님).
- *(이전 방식 — 2026-10-29 ADR 0052 로 팝업 자동 호출로 바뀜. 그때는 엔드포인트가 다른 레인에 있어 아직 없을 수 있었다.)* **정책 근거 추천**은 다른 레인의 `POST /v1/ideas/policy-suggestions` 를 **버튼을 눌렀을 때만** 부른다 — 화면을 열 때마다 404/405 를
  받으면 브라우저 콘솔 오류가 남아 "CSP 아래 콘솔 오류 0" e2e 가 깨진다. 404/405/503 → 영역을 접고 "정책 근거 추천은 정책 자료 적재 뒤 열립니다".
  (405 는 SPA catch-all 이 GET 만 받아서.) 고른 문구만 정책 근거 칸 **뒤에 덧붙고**, 간편 모드였으면 상세 모드로 바꿔 보여 준다.
- **브리핑은 별도 경로 `/new/brief`**(②와 ③ 사이, stepper 는 ②). 결과는 TanStack 캐시(입력 키, staleTime ∞), 고른 chunk_id 만 store 에 — 생성
  요청 `priority_evidence` 로. 건너뜀·503·오류 모두 다음으로 갈 수 있다.
- **근거 패널**은 `<dialog>`(옆 패널 대신 — 360 px 에서 같은 코드). 문장 id 는 초안 응답에 없어 `s:<section>:<index>` 로 만든다. 판단은
  `base_version` 을 붙여 보내고 409 면 "최신 버전 불러오기"(run 캐시 무효화). `?evidence=<sid>` 로 열리고 `#sec-<key>` 앵커로 섹션 이동 —
  제출 전 점검의 target 이 이 두 가지를 쓴다. 이미지 판독 근거의 "원본 보기"는 응답에 URL 이 없어 자료 검색(doc_id)으로 연결했다.
- **AI 다시 쓰기**는 저장하지 않은 편집이 있으면 후보만 보여 주고 반영을 막는다(버전이 바뀌면 편집 기준이 어긋난다). 반영 뒤 편집 상태를 비운다.
- 제출 전 점검은 ⑤와 ⑥ 사이 하위 메뉴. 만족도는 `finalized` 뒤에만 폼을 보이고 422(이메일·전화)는 배너.

## 자체 디자인 검토 (3회)

3. U9: 비교표·다시 쓰기 표는 최소 폭을 두고 컨테이너 안에서만 가로 스크롤(문서 폭 유지), 긴 라벨 배지는 `whitespace-normal`.
   미리보기 칸의 빈 값은 "(비어 있음 — 질문으로 채웁니다)" 로 다음 행동을 적었고, 브리핑 "요약 없음"·공백 "후보" 배지로 모델 출력의
   한계를 표시. 근거 패널의 세 판단 버튼은 편집 화면의 처리 라디오와 같은 모양(라디오 + 라벨)으로 맞췄다.

1. 일관성: 간격(섹션 `space-y-6`, 카드 `p-4/5`)·제목 크기(h1 2xl, h2 lg, h3 base)·배지 색(origin 토큰 4색)을 맞췄고, 스크롤 컨테이너 안의
   `sr-only` 가 문서 폭을 늘리던 문제(360 px 가로 스크롤)를 `relative` 로 고쳤다. 긴 선택지 라벨 배지는 줄바꿈 허용.
2. 빈·로딩·오류 상태: 모든 조회에 Skeleton(높이 예약)·EmptyState·ProblemBanner(problem+json detail) 를 두고, 문장이 없는 섹션에는 사유와
   다음 행동("직접 수정에서 채울 수 있습니다")을 적었다. 토스트는 오류만 `role=alert`, 나머지는 polite. 한국어 문구는 백엔드 검증 문구와 같게
   ("필수 슬롯이 비었습니다: …", "슬롯 길이 n > 2000").
