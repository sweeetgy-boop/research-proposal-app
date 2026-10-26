# ADR 0008 — 웹 프론트엔드는 React SPA (2026-10-26)

**배경** Streamlit 화면은 시연용. 편집·버전 비교·팝업 흐름은 Streamlit 로 어렵다. (대화 기록 기준, 미검증 — `dec519e` 의 정적 SPA 서빙으로 간접 확인)
**선택지** (a) Streamlit 확장, (b) 서버 렌더(Jinja), (c) Vite + React + TypeScript SPA, FastAPI 가 `web/dist` 서빙.
**결정** (c). 세션 쿠키 + CSRF, problem+json, SSE, `docs/openapi.json` 에서 타입 생성. 동료가 `web/` 담당(CODEOWNERS TODO).
**이유** 문장 단위 편집기·diff·팝업·접근성 목표(WCAG 2.2 AA, Lighthouse 95)는 SPA 가 맞다. 외부 요청 없음·CSP 호환.
**결과** 백엔드 REST(세션·CSRF·SSE·가짜 모드)는 준비됨. 근거 `dec519e`, architecture §9.2.
