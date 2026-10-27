# ADR 0015 — 웹 프론트엔드 스택: Vite + React + TypeScript, 네이티브 대화상자, 같은 출처 CSP (2026-10-27)

**배경** ADR 0008 로 React SPA 를 정했고 백엔드 REST(세션 쿠키·CSRF·SSE·problem+json·가짜 모드)가 준비됐다. 화면 11개(①~⑥ 흐름 +
run 목록·검색·자료원)를 WCAG 2.2 AA·Lighthouse 95·번들 200 KB gzip 안에서 만들어야 하고, 백엔드 CSP 는 `script-src 'self'; style-src 'self'`
(인라인 금지)다.
**선택지** (a) Radix 기반 shadcn/ui 그대로, (b) shadcn 스타일 토큰·cva 만 복사하고 대화상자·탭·토스트는 네이티브 요소(`<dialog>`, role 속성)로,
(c) Next.js 같은 프레임워크. 글꼴은 (1) CDN, (2) `pretendard` npm 자체 호스팅(가변·동적 서브셋).
**결정** (b)+(2). Vite 7·React 19·TypeScript strict·Tailwind v4(토큰은 CSS 변수)·TanStack Query/Virtual·react-router 7·`diff`·lucide·
`openapi-typescript`(요청 타입 생성, 응답 타입은 `views.py` 기준 손으로). 테마 초기화는 인라인 스크립트 대신 외부 `theme-init.js`.
e2e 는 가짜 백엔드가 `web/dist` 를 서빙하는 상태에서 돌려 CSP·쿠키·SSE 경로를 그대로 검증한다.
**이유** Radix(react-remove-scroll)는 `<style>` 을 주입해 `style-src 'self'` 와 충돌한다. 네이티브 `<dialog>` 가 포커스 가두기·Esc·배경 inert 를
브라우저에 맡겨 번들도 작다. CDN 글꼴은 허용 도메인 정책(보안 C)과 CSP 에 어긋난다.
**결과** 번들 초기 JS 110.6 KB gzip(전체 JS 약 167 KB, CSS 21.2 KB), Lighthouse 100/100/100(CLS 0), axe 위반 0(7 화면), vitest 33·Playwright 8.
API 토큰은 저장하지 않고 CSRF 만 sessionStorage, 제안자 정보는 마무리 요청 본문으로만.
