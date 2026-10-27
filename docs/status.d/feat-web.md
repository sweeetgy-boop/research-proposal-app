## [3] 웹 프론트엔드 (feat/web, 2026-10-27)

- `web/` Vite 7 + React 19 + TypeScript strict + Tailwind v4(CSS 변수 토큰, 라이트/다크) + TanStack Query/Virtual + react-router 7 + `diff` +
  lucide + Pretendard 자체 호스팅. 백엔드가 `web/dist` 를 같은 출처로 서빙(CSP `'self'`, 인라인 없음). 설계 ADR 0015, 사용법 `web/README.md`.
- 화면 11개: 로그인(토큰 1회·CSRF 만 보관) → ① 아이디어 입력(백엔드와 같은 검증 문구) → ② 유사과제 확인(경보 표·차단 확인란·차별화 제안·
  과제 추천 미리보기/확정/원래 아이디어/다시 받기) → ③ 보강 질문(0개면 바로 생성) → 생성 진행(SSE 이름 이벤트·재접속) → 초안 보기(v1/v2·
  근거·origin 배지·알림·인용·Argon 1차 검토 점수/의견/후보·설계도) → ④ DraftEditor(use_revision/manual/delete/insert_after·섹션 통문·메모·
  처리됨·서버 자동 임시 저장·409 충돌 대화상자) → 버전 목록(가상화)·글자 단위 diff·복원 → ⑤ 최종 검토(점수 변화·stale n건·다시 받기) →
  ⑥ 최종 마무리(선택형 확정·제안자 정보는 요청 본문으로만·렌더 점검·HWPX 내려받기·다시 열기) + run 목록·자료 검색·자료원 상태.
- 측정: Lighthouse 100/100/100(CLS 0), axe 위반 0(7 화면), 초기 JS 110.6 KB gzip(전체 ≈167 KB), Vitest 33, Playwright 8(가짜 백엔드,
  ①→⑥ 파일 내려받기까지). 캡처 `docs/screens/`·`docs/history/screens/2026-10-27-web-*.png`, 녹화 `docs/history/demo/2026-10-27-web-full-flow.webm`.
- CI: 기존 `web` job(npm ci·lint·typecheck·test) 그대로. e2e·Lighthouse 는 로컬(`npm run e2e`, `npm run lighthouse`).
- 남은 일: 추천 ≥1건·clarify 질문 ≥1개·review_skipped(키 없음) 경로는 가짜 모드에서 재현되지 않아 단위 테스트(fixture)만. 백엔드 영향은 PR 본문 참조.
