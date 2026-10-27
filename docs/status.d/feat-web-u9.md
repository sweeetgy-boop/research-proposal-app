## [U9] 웹 반영 — U1~U8 화면 (feat/web-u9, 2026-10-27)

- 기준: main 32dcaf0(PR #27) → 작업 중 main(PR #28 이미지 판독) 병합. `rra api schema` 41 경로·`npm run gen:api` 재생성(응답 타입은
  `web/src/api/types.ts` 손으로). 가짜 백엔드: `adapters/fake/llm.py` 에 간편 입력(`[자유 입력`)·브리핑(`[선행연구`) 프롬프트 분기 추가 —
  e2e 가 U2·U5 경로를 지난다(원문 그대로 칸에 넣어 근거 검사 통과, 요약은 수치 없음).
- 화면: ① 간편 입력(기본; 네 칸 미리보기·보완 질문 0~4·답 합치기·건너뛰기·상세 입력에 채우기·503 → 상세) + 정책 근거 추천(버튼 호출,
  404/405/503 → 접힌 안내; 클라이언트 `api/policySuggestions.ts` 한 파일) → ② 차별성 비교표(제안 과제 + 상위 5 × 5 관점, "정보 없음(제목 기준)",
  추천 카드 `#rec-<n>` 링크) → `/new/brief` 선행연구 브리핑(10건 한 줄 요약/요약 없음, 연도 CSS 막대, 주제어, "후보" 라벨 공백, 체크 →
  `priority_evidence`) → 초안 보기 근거 패널(`<dialog>`: 발췌·제목·자료원·기관·연도·수집일·근거 수준 + 세부 확인 필요·이미지 판독(원본 = 자료 검색)·
  전략체계 초안(확인 전)·Argon 지지/부분/불일치·승인/교체(검색 집합 id)/제외 → 새 버전, 409 → 최신 버전 불러오기, evidence_mismatch/
  evidence_all_excluded 알림; `?evidence=<sid>`·`#sec-<key>`) → ④ 편집 섹션 머리 [AI 다시 쓰기](현재·후보 나란히·보존 배지·체크 → 반영,
  503/409 안내, 임시 편집 있으면 반영 차단) [보완 질문](충족률·답 저장) → ⑤ 최종 검토 → `/runs/:id/submit-check` 제출 전 점검(9 항목 통과/
  확인 필요·건수·detail, 누르면 target 으로; 사용 기록; finalized 뒤 만족도 1~5+한 줄 → feedback, 422 배너) → ⑥. stepper 라벨에 sr-only 힌트.
- 검사: `npm run lint`·`typecheck` 통과, Vitest 50(13 파일, 새 7 파일·axe 8 화면 위반 0), Playwright 10(기존 8 + U9 전체 흐름·503 대체,
  가짜 백엔드), `npm run build` 초기 JS 111.6 KB gzip(전체 ≈184 KB), Lighthouse `/login` 100/100/100(CLS 0). 백엔드 tests/entrypoints·adapters
  779 통과, lint-imports 8 kept, ruff 통과.
- 캡처 `docs/screens/15~22-*.png`(기존 01~14 재캡처)·`docs/history/screens/2026-10-27-web-u9-01~08.png`, 녹화 `docs/history/demo/2026-10-27-web-u9-flow.webm`(536 KB).
- API 차이·미비(통합 세션 참고):
  - `GET /v1/runs/{id}/draft` 문장에 `sentence_id` 없음 → 화면이 `s:<section>:<index>` 로 만든다 (`version_payload` 에는 있음).
  - `POST /v1/runs` 에 `acknowledged`·`supplement` 없음(feat/draft-quality 에만) — 화면은 `supplement` 를 보내지만 main 은 무시한다(ProposalRequest 가 extra 를 막지 않음). 타입은 `ProposalRequest & { supplement?: string }` 로 둠.
  - `GET …/sentences/{sid}/evidence` 이미지 판독 근거에 원본 URL(`raw.image.url`) 이 없어 "원본 보기"는 자료 검색(doc_id) 링크. 가짜 모드 `support` 는 항상 `{}`(ScriptedReviewLLM 이 support 를 안 줌) — 단위 테스트 fixture 로만 확인.
  - `POST /v1/ideas/policy-suggestions` 는 main 에 없음(405: SPA catch-all 은 GET 만) → 미개방 처리. 기대 모양 `{items:[{document,year,page,quote,url}]}`.
  - `strategy_source=draft` 표시는 submit-check 의 `strategy_source` 항목 `source` 로 읽는다(별도 settings 엔드포인트 없음).
- 하지 않은 것: 로그인 뒤 화면 Lighthouse(인증 게이트가 sessionStorage CSRF 라 쿠키 헤더만으로는 `/login` 으로 감 — README 기록), ADR(결정은
  web/README.md "U9 설계 메모"에 — 별도 ADR 감은 아님), 가상화된 초안(60행 초과)에서 `#sec-` 앵커는 DOM 에 없을 수 있음(가짜·골든셋 15행은 해당 없음).
